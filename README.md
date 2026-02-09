# CodeMCQ Arena

A futuristic MCQ + coding question practice platform with login, dashboard, quizzes, coding challenges, results, and a fully animated neon-themed UI.

## 🚀 Features

- **User Authentication**: Signup, Login, and Logout with secure password hashing
- **Personalized Dashboard**: View stats, recent attempts, and quick access to quizzes
- **MCQ Quizzes**: Multi-language, multi-level quizzes loaded from modular JSON files
- **Coding Challenges**: Programming problems with code editor interface
- **Results & Analytics**: Detailed quiz results with score breakdown and question review
- **Futuristic UI**: Neon-themed dark interface with smooth animations and transitions
- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile devices

## 🌐 Supported MCQ Languages

`html`, `css`, `javascript`, `java`, `php`, `dsa`, `python`, `nextjs`, `nodejs`, `react`, `c`, `cpp (C++)`, `csharp (C#)`, `operating_system`

> Use the slug shown above when creating files. The UI automatically renders friendly labels (e.g., `cpp` → “C++”, `csharp` → “C#”, `operating_system` → “Operating System”).

## 📋 Prerequisites

- Python 3.7 or higher
- pip (Python package installer)

## 🛠️ Installation

1. **Clone or download this project**

2. **Navigate to the project directory**
   ```bash
   cd "Untitled Folder"
   ```

3. **Create a virtual environment (recommended)**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## ▶️ Running the Application

1. **Start the Flask server**
   ```bash
   python app.py
   ```

2. **Open your browser and navigate to**
   ```
   http://localhost:5000
   ```

3. **Create an account** or **login** to start using the platform

## 📁 Project Structure

```
CodeMCQ Arena/
│
├── app.py                 # Main Flask application
├── data_loader.py         # JSON data loading functions
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── codemcq.db            # SQLite database (created automatically)
│
├── templates/            # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── signup.html
│   ├── dashboard.html
│   ├── quiz_select.html
│   ├── quiz_question.html
│   ├── result.html
│   ├── coding_list.html
│   └── coding_challenge.html
│
├── static/
│   ├── css/
│   │   └── style.css     # Futuristic neon theme styles
│   └── js/
│       └── main.js       # JavaScript for interactions and animations
│
└── data/
    ├── mcq/              # per language + level JSON quizzes
    │   ├── html/easy.json
    │   ├── ...
    │   ├── python/{easy|medium|hard}.json
    │   ├── nextjs/{easy|medium|hard}.json
    │   ├── nodejs/{easy|medium|hard}.json
    │   ├── react/{easy|medium|hard}.json
    │   ├── c/{easy|medium|hard}.json
    │   ├── cpp/{easy|medium|hard}.json
    │   ├── csharp/{easy|medium|hard}.json
    │   └── operating_system/{easy|medium|hard}.json
    └── coding_challenges.json  # Coding challenges with language + level
```

## 📝 Adding More MCQ Quizzes

Quizzes now live in `data/mcq/<language>/<level>.json`. Each combination (e.g., `html/easy.json`) represents one quiz. To add or edit a quiz:

1. Pick the correct language folder (`html`, `css`, `javascript`, `java`, `php`, `dsa`, `python`, `nextjs`, `nodejs`, `react`, `c`, `cpp`, `csharp`, `operating_system`).
2. Create or edit the `easy.json`, `medium.json`, or `hard.json` file.
3. Use the schema below (1 quiz per file, ≥10 questions, 4 options each).

```json
{
  "quiz_id": "html_easy",
  "language": "html",
  "level": "easy",
  "title": "HTML Basics - Easy",
  "description": "Fundamental questions on HTML tags and structure.",
  "duration_minutes": 15,
  "difficulty": "easy",
  "questions": [
    {
      "id": 1,
      "question_text": "What does HTML stand for?",
      "options": [
        { "id": "a", "text": "Hyper Text Markup Language", "is_correct": true },
        { "id": "b", "text": "High Tool Markup Language", "is_correct": false },
        { "id": "c", "text": "Hyperlink Text Making Language", "is_correct": false },
        { "id": "d", "text": "Home Tool Markup Level", "is_correct": false }
      ]
    }
  ]
}
```

**Important Notes:**
- File name must match level (`easy.json`, `medium.json`, `hard.json`) inside the language folder.
- `quiz_id` should follow `<language>_<level>` to match routing (e.g., `css_hard`).
- Each file needs at least 10 questions, with unique `id` values.
- Provide exactly four options per question, with a single `is_correct: true`.

## 💻 Adding More Coding Challenges

To add more coding challenges, edit `data/coding_challenges.json`:

```json
{
  "challenges": [
    {
      "id": "your_challenge_id",
      "title": "Challenge Title",
      "description": "Challenge description and instructions",
      "language": "javascript",
      "level": "medium",
      "sample_input": "example input",
      "sample_output": "example output",
      "difficulty": "easy",
      "test_cases": [
        {
          "input": "test input",
          "output": "expected output"
        }
      ]
    }
  ]
}
```

## 🎨 Customizing the UI

### Colors

Edit CSS variables in `static/css/style.css`:

```css
:root {
    --bg-primary: #030712;
    --neon-blue: #00d9ff;
    --neon-purple: #a855f7;
    --neon-pink: #ec4899;
    /* ... more variables */
}
```

### Animations

Animations are defined in `static/css/style.css` using `@keyframes`. You can modify or add new animations as needed.

## 🔒 Security Notes

- **Change the secret key** in `app.py` before deploying to production:
  ```python
  app.secret_key = 'your-secret-key-change-in-production'
  ```
- Use environment variables for sensitive data in production
- Consider using a production WSGI server (e.g., Gunicorn) instead of Flask's development server

## 🗄️ Database

The application uses SQLite database (`codemcq.db`) which is created automatically on first run. The database includes:

- **users**: User accounts with hashed passwords
- **attempts**: Quiz attempt records
- **attempt_answers**: Individual question answers
- **coding_submissions**: Coding challenge submissions

## 🚀 Expanding the Project

### Adding Code Execution

Currently, coding challenges only save submissions. To add actual code execution:

1. Create a new route in `app.py` for code execution
2. Use a sandboxed environment (e.g., Docker, PyPy sandbox)
3. Implement test case validation
4. Update the frontend to display execution results

### Adding More Features

- **Leaderboards**: Add ranking system based on scores
- **Categories**: Organize quizzes by topics
- **Progress Tracking**: Track user progress over time
- **Social Features**: Share results, compare with friends
- **Admin Panel**: Manage quizzes and users
- **Email Notifications**: Send results via email

## 🐛 Troubleshooting

### Database Errors
- Delete `codemcq.db` and restart the app to recreate the database
- Ensure you have write permissions in the project directory

### Port Already in Use
- Change the port in `app.py`: `app.run(debug=True, port=5001)`

### JSON Errors
- Validate your JSON files using an online JSON validator
- Ensure proper syntax (commas, quotes, brackets)

## 📄 License

This project is open source and available for educational purposes.

## 👨‍💻 Development

### Running in Development Mode

The app runs in debug mode by default. For production:

1. Set `debug=False` in `app.py`
2. Use a production WSGI server
3. Configure proper error handling and logging

### Testing

To test the application:

1. Create a test account
2. Take a quiz and verify results
3. Submit a coding challenge
4. Check dashboard stats

## 📞 Support

For issues or questions:
1. Check the JSON file formats
2. Verify database permissions
3. Review Flask error messages in the terminal

---

**Enjoy coding and competing on CodeMCQ Arena! 🎮✨**

