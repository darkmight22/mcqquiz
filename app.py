from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
import random
import smtplib
from datetime import datetime, timedelta
from data_loader import (
    LANGUAGES,
    LEVELS,
    LANGUAGE_LABELS,
    load_quiz,
    load_quiz_catalog,
    get_quiz_by_id,
    get_question_by_index,
    get_challenges_by_language_and_level,
    get_challenge,
    get_language_label,
)
app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'  # Change this in production!
app.config['DATABASE'] = 'codemcq.db'

EMAIL_USER = 'darkmight2242@gmail.com'
EMAIL_PASSWORD = 'jfkn dgus pigr ltcp '  # Use Gmail App Password or similar
OTP_EXPIRY_MINUTES = 5
# In production consider moving these limits into config and pairing with
# per-IP throttling to prevent OTP brute force attacks.
MAX_OTP_ATTEMPTS = 3
DISPOSABLE_DOMAINS = [
    "mailinator.com",
    "10minutemail.com",
    "guerrillamail.com",
    "tempmail.com",
]


@app.context_processor
def inject_language_labels():
    return {
        'language_labels': LANGUAGE_LABELS,
        'get_language_label': get_language_label
    }

# Initialize database
def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        email_verified INTEGER DEFAULT 0,
        otp_code TEXT,
        otp_expires_at TIMESTAMP,
        otp_attempts INTEGER DEFAULT 0
    )''')
    
    # Ensure legacy databases get the new columns when missing
    c.execute('PRAGMA table_info(users)')
    existing_columns = {row[1] for row in c.fetchall()}
    if 'email_verified' not in existing_columns:
        c.execute('ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0')
    if 'otp_code' not in existing_columns:
        c.execute('ALTER TABLE users ADD COLUMN otp_code TEXT')
    if 'otp_expires_at' not in existing_columns:
        c.execute('ALTER TABLE users ADD COLUMN otp_expires_at TIMESTAMP')
    if 'otp_attempts' not in existing_columns:
        c.execute('ALTER TABLE users ADD COLUMN otp_attempts INTEGER DEFAULT 0')
    
    # Attempts table
    c.execute('''CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        quiz_id TEXT NOT NULL,
        score INTEGER DEFAULT 0,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        total_correct INTEGER DEFAULT 0,
        total_wrong INTEGER DEFAULT 0,
        total_unanswered INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    # Attempt answers table
    c.execute('''CREATE TABLE IF NOT EXISTS attempt_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attempt_id INTEGER NOT NULL,
        quiz_id TEXT NOT NULL,
        question_id INTEGER NOT NULL,
        selected_option_id TEXT,
        is_correct INTEGER DEFAULT 0,
        FOREIGN KEY (attempt_id) REFERENCES attempts (id)
    )''')
    
    # Coding submissions table
    c.execute('''CREATE TABLE IF NOT EXISTS coding_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        challenge_id TEXT NOT NULL,
        code TEXT,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    conn.commit()
    conn.close()

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn


def generate_otp():
    """Return a 6-digit OTP"""
    return f"{random.randint(100000, 999999)}"


def send_otp_email(to_email, otp):
    """Send the OTP email via Gmail SMTP"""
    subject = "CodeMCQ Arena Email Verification OTP"
    body = (
        f"Your OTP for verifying CodeMCQ Arena is {otp}.\n\n"
        f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n"
        "If you did not request this, please ignore the email.\n"
        "Only 3 attempts are provided.\n"
        "After 3 attempts are over please wait for 5 minutes to resend OTP.\n\n"
    )
    # Include From header and basic MIME to improve deliverability
    message = f"From: CodeMCQ Arena <{EMAIL_USER}>\nSubject: {subject}\n\n{body}"

    try:
        # Use SMTP_SSL which is compatible with Gmail's 465 port
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, to_email, message)
    except Exception as exc:
        # Log the exception with helpful hints for debugging
        app.logger.exception(
            "Failed to send OTP email to %s: %s.\nHints: ensure EMAIL_USER and EMAIL_PASSWORD are correct, "
            "that Gmail account allows SMTP access (use an app password for accounts with 2FA), "
            "and that network outbound SMTP is allowed.",
            to_email,
            exc,
        )
        raise


def is_disposable_email(email):
    """Check if email domain is in the disposable list"""
    if '@' not in email:
        return False
    domain = email.split('@')[-1].lower()
    return domain in DISPOSABLE_DOMAINS


def set_user_session(user):
    """Log the user into the current session."""
    session['user_id'] = user['id']
    session['user_name'] = user['name']
    session['user_email'] = user['email']
    session['is_verified'] = bool(user['email_verified'])


def set_pending_verification(email, user_id):
    """Persist pending verification info in session for convenience."""
    session['pending_verification_email'] = email
    session['pending_user_id'] = user_id


def refresh_otp_for_user(user_id):
    """Generate and store a new OTP for the given user."""
    otp = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    conn = get_db()
    c = conn.cursor()
    c.execute(
        'UPDATE users SET otp_code = ?, otp_expires_at = ?, otp_attempts = 0 WHERE id = ?',
        (otp, expires_at.isoformat(), user_id)
    )
    conn.commit()
    conn.close()
    return otp


def parse_db_timestamp(value):
    """Best-effort conversion from SQLite stored timestamp to datetime"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def parse_quiz_identifier(quiz_id):
    """Return (language, level) tuple from quiz identifier."""
    if not quiz_id or '_' not in quiz_id:
        return None, None
    return quiz_id.rsplit('_', 1)

def require_login(f):
    """Decorator to require login"""
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'error')
            return redirect(url_for('login'))
        
        if not session.get('is_verified'):
            # Double-check with DB in case session is stale
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT email_verified, email FROM users WHERE id = ?', (session['user_id'],))
            user = c.fetchone()
            conn.close()
            if user and user['email_verified']:
                session['is_verified'] = True
            else:
                pending_email = user['email'] if user else session.get('user_email')
                if pending_email:
                    set_pending_verification(pending_email, session.get('user_id'))
                flash('Please verify your email before accessing this area.', 'error')
                return redirect(url_for('verify_email'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Routes
@app.route('/')
def index():
    """Landing page"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """User registration"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not name or not email or not password:
            flash('All fields are required.', 'error')
            return render_template('signup.html', name=name, email=email)
        
        if len(password) <= 8:
            flash('Password must be at least 8 or long characters long.', 'error')
            return render_template('signup.html', name=name, email=email)
        
        if is_disposable_email(email):
            flash('Disposable / temporary email addresses are not allowed. Please use a real email.', 'error')
            return render_template('signup.html', name=name, email=email)
        
        conn = get_db()
        c = conn.cursor()
        
        # Check if email already exists
        c.execute('SELECT id FROM users WHERE email = ?', (email,))
        if c.fetchone():
            conn.close()
            flash('Email already registered. Please login.', 'error')
            return render_template('signup.html', name=name, email=email)
        
        # Create new user
        password_hash = generate_password_hash(password)
        c.execute('INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
                  (name, email, password_hash))
        user_id = c.lastrowid
        
        otp = generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
        c.execute(
            'UPDATE users SET otp_code = ?, otp_expires_at = ?, otp_attempts = 0 WHERE id = ?',
            (otp, expires_at.isoformat(), user_id)
        )
        conn.commit()
        conn.close()
        
        set_pending_verification(email, user_id)
        
        try:
            send_otp_email(email, otp)
            flash('Account created! Enter the OTP we sent to verify your email.', 'success')
        except Exception:
            flash('Account created but we could not send the OTP email. Please click "Resend OTP" after verifying your email settings.', 'error')
        
        return redirect(url_for('verify_email'))
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('login.html', email=email)
        
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id, name, email, password_hash, email_verified FROM users WHERE email = ?', (email,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            if not user['email_verified']:
                set_pending_verification(user['email'], user['id'])
                flash('Please verify your email using the OTP sent to you before logging in.', 'error')
                return redirect(url_for('verify_email'))
            
            set_user_session(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')
            return render_template('login.html', email=email)
    
    return render_template('login.html')


@app.route('/verify-email', methods=['GET', 'POST'])
def verify_email():
    """Verify user email using OTP"""
    if session.get('user_id') and session.get('is_verified'):
        flash('Your email is already verified.', 'info')
        return redirect(url_for('dashboard'))
    
    query_email = (request.args.get('email') or '').strip()
    if query_email:
        session['pending_verification_email'] = query_email
    email = query_email or session.get('pending_verification_email', '')
    
    if request.method == 'POST':
        email = (request.form.get('email') or email or '').strip()
        otp = request.form.get('otp', '').strip()
        
        if not email or not otp:
            flash('Email and OTP are required.', 'error')
            return render_template('verify_email.html', email=email, otp_expiry_minutes=OTP_EXPIRY_MINUTES)
        
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            SELECT id, name, email, email_verified, otp_code, otp_expires_at, otp_attempts
            FROM users
            WHERE email = ?
        ''', (email,))
        user = c.fetchone()
        
        if not user:
            conn.close()
            flash('Account not found for the provided email.', 'error')
            return render_template('verify_email.html', email=email, otp_expiry_minutes=OTP_EXPIRY_MINUTES)
        
        if user['email_verified']:
            conn.close()
            set_user_session(user)
            flash('Email already verified. You are logged in!', 'success')
            return redirect(url_for('dashboard'))
        
        expires_at = parse_db_timestamp(user['otp_expires_at'])
        if not user['otp_code']:
            conn.close()
            flash('No OTP found. Please resend the OTP.', 'error')
            set_pending_verification(email, user['id'])
            return render_template('verify_email.html', email=email, otp_expiry_minutes=OTP_EXPIRY_MINUTES)
        
        if not expires_at or datetime.utcnow() > expires_at:
            conn.close()
            flash('OTP expired. Please resend a new OTP.', 'error')
            set_pending_verification(email, user['id'])
            return render_template('verify_email.html', email=email, otp_expiry_minutes=OTP_EXPIRY_MINUTES)
        
        if otp != user['otp_code']:
            attempts = (user['otp_attempts'] or 0) + 1
            c.execute('UPDATE users SET otp_attempts = ? WHERE id = ?', (attempts, user['id']))
            conn.commit()
            conn.close()
            if attempts >= MAX_OTP_ATTEMPTS:
                flash('Too many incorrect attempts. Please resend OTP.', 'error')
            else:
                flash('Invalid OTP. Please try again.', 'error')
            set_pending_verification(email, user['id'])
            return render_template('verify_email.html', email=email, otp_expiry_minutes=OTP_EXPIRY_MINUTES)
        
        c.execute('''
            UPDATE users
            SET email_verified = 1,
                otp_code = NULL,
                otp_expires_at = NULL,
                otp_attempts = 0
            WHERE id = ?
        ''', (user['id'],))
        conn.commit()
        conn.close()
        
        user_data = dict(user)
        user_data['email_verified'] = 1
        set_user_session(user_data)
        session.pop('pending_verification_email', None)
        session.pop('pending_user_id', None)
        
        flash('Email verified! Welcome to CodeMCQ Arena.', 'success')
        return redirect(url_for('dashboard'))
    
    if not email:
        flash('No email to verify. Please sign up or log in.', 'error')
        return redirect(url_for('signup'))
    
    return render_template('verify_email.html', email=email, otp_expiry_minutes=OTP_EXPIRY_MINUTES)


@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    """Regenerate and send a new OTP to the user's email"""
    # Consider adding per-user/IP cooldowns before allowing another resend.
    session_email = session.get('pending_verification_email') or ''
    email = request.form.get('email', '').strip() or session_email.strip()
    
    if not email:
        flash('Provide an email to resend the OTP.', 'error')
        return redirect(url_for('signup'))
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, email_verified FROM users WHERE email = ?', (email,))
    user = c.fetchone()
    conn.close()
    
    if not user:
        flash('Account not found. Please sign up.', 'error')
        return redirect(url_for('signup'))
    
    if user['email_verified']:
        flash('Email already verified. Please log in.', 'info')
        return redirect(url_for('login'))
    
    otp = refresh_otp_for_user(user['id'])
    try:
        send_otp_email(email, otp)
        flash('A new OTP has been sent to your email.', 'success')
    except Exception:
        flash('Failed to send OTP. Please try again later.', 'error')
    
    set_pending_verification(email, user['id'])
    return redirect(url_for('verify_email'))

@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
@require_login
def dashboard():
    """User dashboard"""
    conn = get_db()
    c = conn.cursor()
    
    # Get user stats
    c.execute('''
        SELECT 
            COUNT(*) as total_attempts,
            MAX(score) as best_score,
            AVG(score) as avg_score
        FROM attempts
        WHERE user_id = ?
    ''', (session['user_id'],))
    stats = c.fetchone()
    
    # Get recent attempts
    c.execute('''
        SELECT a.*
        FROM attempts a
        WHERE a.user_id = ?
        ORDER BY COALESCE(a.completed_at, a.started_at) DESC
        LIMIT 5
    ''', (session['user_id'],))
    recent_attempts = c.fetchall()
    
    conn.close()
    
    # Get quiz titles from JSON
    quiz_catalog = load_quiz_catalog()
    quiz_titles = {q['id']: q['title'] for q in quiz_catalog}
    
    # Update recent attempts with proper titles
    attempts_list = []
    for attempt in recent_attempts:
        attempt_dict = dict(attempt)
        attempt_dict['quiz_title'] = quiz_titles.get(attempt_dict['quiz_id'], attempt_dict['quiz_id'])
        attempts_list.append(attempt_dict)
    
    return render_template('dashboard.html',
                         stats=stats,
                         recent_attempts=attempts_list,
                         user_name=session['user_name'],
                         quiz_catalog=quiz_catalog)

@app.route('/quiz/list')
@require_login
def quiz_list():
    """Legacy route - redirect to new selection page"""
    return redirect(url_for('quiz_select'))


@app.route('/quiz/select', methods=['GET', 'POST'])
@require_login
def quiz_select():
    """Interactive quiz selection by language and level."""
    if request.method == 'POST':
        language = request.form.get('language', '').lower()
        level = request.form.get('level', '').lower()
        if language not in LANGUAGES or level not in LEVELS:
            flash('Please choose a valid language and level.', 'error')
            return redirect(url_for('quiz_select'))
        return redirect(url_for('quiz_start', language=language, level=level))

    selected_language = request.args.get('language', '').lower()
    if selected_language and selected_language not in LANGUAGES:
        selected_language = ''

    selected_level = request.args.get('level', '').lower()
    if selected_level and selected_level not in LEVELS:
        selected_level = ''

    selected_quiz = None
    if selected_language and selected_level:
        selected_quiz = load_quiz(selected_language, selected_level)
    quiz_catalog = load_quiz_catalog()

    return render_template(
        'quiz_select.html',
        languages=LANGUAGES,
        levels=LEVELS,
        selected_language=selected_language,
        selected_level=selected_level,
        selected_quiz=selected_quiz,
        quiz_catalog=quiz_catalog
    )

@app.route('/quiz/start/<language>/<level>')
@require_login
def quiz_start(language, level):
    """Start a quiz - create attempt and redirect to first question"""
    language = language.lower()
    level = level.lower()
    if language not in LANGUAGES or level not in LEVELS:
        flash('Invalid quiz selection.', 'error')
        return redirect(url_for('quiz_select'))

    quiz = load_quiz(language, level)
    if not quiz:
        flash('Quiz not found.', 'error')
        return redirect(url_for('quiz_select'))

    quiz_id = quiz.get('quiz_id') or f"{language.lower()}_{level.lower()}"
    
    conn = get_db()
    c = conn.cursor()
    
    # Create new attempt
    c.execute('''
        INSERT INTO attempts (user_id, quiz_id, started_at)
        VALUES (?, ?, ?)
    ''', (session['user_id'], quiz_id, datetime.now()))
    attempt_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return redirect(url_for('quiz_question', attempt_id=attempt_id, q_no=0))

@app.route('/quiz/question/<int:attempt_id>/<int:q_no>', methods=['GET', 'POST'])
@require_login
def quiz_question(attempt_id, q_no):
    """Display and handle quiz question"""
    conn = get_db()
    c = conn.cursor()
    
    # Verify attempt belongs to user
    c.execute('SELECT * FROM attempts WHERE id = ? AND user_id = ?', (attempt_id, session['user_id']))
    attempt = c.fetchone()
    if not attempt:
        conn.close()
        flash('Attempt not found.', 'error')
        return redirect(url_for('quiz_select'))
    
    quiz = get_quiz_by_id(attempt['quiz_id'])
    if not quiz:
        conn.close()
        flash('Quiz not found.', 'error')
        return redirect(url_for('quiz_select'))
    
    quiz_identifier = quiz.get('quiz_id') or attempt['quiz_id']
    questions = quiz.get('questions', [])
    total_questions = len(questions)
    
    if q_no < 0 or q_no >= total_questions:
        conn.close()
        return redirect(url_for('quiz_submit', attempt_id=attempt_id))
    
    question = get_question_by_index(quiz, q_no)
    if not question:
        conn.close()
        return redirect(url_for('quiz_submit', attempt_id=attempt_id))
    
    # Handle POST (save answer)
    if request.method == 'POST':
        selected_option = request.form.get('option')
        
        # Check if answer already exists
        c.execute('''
            SELECT id FROM attempt_answers
            WHERE attempt_id = ? AND question_id = ?
        ''', (attempt_id, question['id']))
        existing = c.fetchone()
        
        # Find correct option
        correct_option = None
        for opt in question['options']:
            if opt['is_correct']:
                correct_option = opt['id']
                break
        
        is_correct = 1 if selected_option == correct_option else 0
        
        if existing:
            # Update existing answer
            c.execute('''
                UPDATE attempt_answers
                SET selected_option_id = ?, is_correct = ?
                WHERE attempt_id = ? AND question_id = ?
            ''', (selected_option, is_correct, attempt_id, question['id']))
        else:
            # Insert new answer
            c.execute('''
                INSERT INTO attempt_answers (attempt_id, quiz_id, question_id, selected_option_id, is_correct)
                VALUES (?, ?, ?, ?, ?)
            ''', (attempt_id, quiz_identifier, question['id'], selected_option, is_correct))
        
        conn.commit()
        
        # Redirect to next question or submit
        if q_no + 1 < total_questions:
            conn.close()
            return redirect(url_for('quiz_question', attempt_id=attempt_id, q_no=q_no + 1))
        else:
            conn.close()
            return redirect(url_for('quiz_submit', attempt_id=attempt_id))
    
    # Get saved answer for this question
    c.execute('''
        SELECT selected_option_id FROM attempt_answers
        WHERE attempt_id = ? AND question_id = ?
    ''', (attempt_id, question['id']))
    saved_answer = c.fetchone()
    selected_option = saved_answer['selected_option_id'] if saved_answer else None
    
    # Calculate time remaining
    duration = timedelta(minutes=quiz.get('duration_minutes', 15))
    started_at = datetime.fromisoformat(attempt['started_at']) if isinstance(attempt['started_at'], str) else attempt['started_at']
    elapsed = datetime.now() - started_at
    remaining = duration - elapsed
    seconds_remaining = max(0, int(remaining.total_seconds()))
    
    conn.close()
    
    return render_template('quiz_question.html',
                         quiz=quiz,
                         question=question,
                         q_no=q_no,
                         total_questions=total_questions,
                         attempt_id=attempt_id,
                         selected_option=selected_option,
                         seconds_remaining=seconds_remaining)

@app.route('/quiz/submit/<int:attempt_id>')
@require_login
def quiz_submit(attempt_id):
    """Submit quiz and calculate results"""
    conn = get_db()
    c = conn.cursor()
    
    # Verify attempt
    c.execute('SELECT * FROM attempts WHERE id = ? AND user_id = ?', (attempt_id, session['user_id']))
    attempt = c.fetchone()
    if not attempt:
        conn.close()
        flash('Attempt not found.', 'error')
        return redirect(url_for('quiz_select'))
    
    # If already completed, redirect to results
    if attempt['completed_at']:
        conn.close()
        return redirect(url_for('result', attempt_id=attempt_id))
    
    quiz = get_quiz_by_id(attempt['quiz_id'])
    if not quiz:
        conn.close()
        flash('Quiz not found.', 'error')
        return redirect(url_for('quiz_select'))
    
    # Calculate score
    questions = quiz.get('questions', [])
    total_questions = len(questions)
    correct = 0
    wrong = 0
    unanswered = 0
    
    for question in questions:
        c.execute('''
            SELECT selected_option_id, is_correct FROM attempt_answers
            WHERE attempt_id = ? AND question_id = ?
        ''', (attempt_id, question['id']))
        answer = c.fetchone()
        
        if not answer or not answer['selected_option_id']:
            unanswered += 1
        elif answer['is_correct']:
            correct += 1
        else:
            wrong += 1
    
    score = correct
    total_correct = correct
    total_wrong = wrong
    total_unanswered = unanswered
    
    # Update attempt
    c.execute('''
        UPDATE attempts
        SET score = ?, completed_at = ?, total_correct = ?, total_wrong = ?, total_unanswered = ?
        WHERE id = ?
    ''', (score, datetime.now(), total_correct, total_wrong, total_unanswered, attempt_id))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('result', attempt_id=attempt_id))

@app.route('/result/<int:attempt_id>')
@require_login
def result(attempt_id):
    """Display quiz results"""
    conn = get_db()
    c = conn.cursor()
    
    # Get attempt
    c.execute('SELECT * FROM attempts WHERE id = ? AND user_id = ?', (attempt_id, session['user_id']))
    attempt = c.fetchone()
    if not attempt:
        conn.close()
        flash('Attempt not found.', 'error')
        return redirect(url_for('quiz_select'))
    
    quiz = get_quiz_by_id(attempt['quiz_id'])
    if not quiz:
        conn.close()
        flash('Quiz not found.', 'error')
        return redirect(url_for('quiz_select'))
    
    # Get all answers
    questions = quiz.get('questions', [])
    results = []
    
    for question in questions:
        c.execute('''
            SELECT selected_option_id, is_correct FROM attempt_answers
            WHERE attempt_id = ? AND question_id = ?
        ''', (attempt_id, question['id']))
        answer = c.fetchone()
        
        selected_option_id = answer['selected_option_id'] if answer else None
        correct_option_id = None
        for opt in question['options']:
            if opt['is_correct']:
                correct_option_id = opt['id']
                break
        
        results.append({
            'question': question,
            'selected_option_id': selected_option_id,
            'correct_option_id': correct_option_id,
            'is_correct': answer['is_correct'] if answer else False
        })
    
    conn.close()
    
    return render_template('result.html',
                         attempt=dict(attempt),
                         quiz=quiz,
                         results=results)

@app.route('/coding/list')
@require_login
def coding_list():
    """List coding challenges with language/level filters"""
    selected_language = request.args.get('language', '').lower() or None
    if selected_language and selected_language not in LANGUAGES:
        selected_language = None

    selected_level = request.args.get('level', '').lower() or None
    if selected_level and selected_level not in LEVELS:
        selected_level = None

    challenges = get_challenges_by_language_and_level(selected_language, selected_level)

    return render_template(
        'coding_list.html',
        challenges=challenges,
        languages=LANGUAGES,
        levels=LEVELS,
        selected_language=selected_language,
        selected_level=selected_level
    )

@app.route('/coding/start/<challenge_id>')
@require_login
def coding_start(challenge_id):
    """Start a coding challenge"""
    challenge = get_challenge(challenge_id)
    if not challenge:
        flash('Challenge not found.', 'error')
        return redirect(url_for('coding_list'))
    
    return render_template('coding_challenge.html', challenge=challenge)

@app.route('/coding/submit', methods=['POST'])
@require_login
def coding_submit():
    """Submit coding challenge solution"""
    challenge_id = request.form.get('challenge_id')
    code = request.form.get('code', '')
    
    if not challenge_id:
        return jsonify({'error': 'Challenge ID required'}), 400
    
    challenge = get_challenge(challenge_id)
    if not challenge:
        return jsonify({'error': 'Challenge not found'}), 404
    
    # Save submission
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO coding_submissions (user_id, challenge_id, code)
        VALUES (?, ?, ?)
    ''', (session['user_id'], challenge_id, code))
    conn.commit()
    conn.close()
    
    # Note: Actual code execution/evaluation would be implemented here
    # For now, we just save the submission
    
    return jsonify({'message': 'Submission saved successfully!'})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5011)

