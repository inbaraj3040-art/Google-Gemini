import os, sqlite3
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")
DB = "edugenie.db"
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, feature TEXT, prompt TEXT,
        response TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    con.commit(); con.close()

def ai_generate(prompt):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return "Gemini API key இல்லை. .env file-ல் GEMINI_API_KEY அமைத்து மீண்டும் முயற்சிக்கவும்."
    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )
        return response.text or "AI response கிடைக்கவில்லை."
    except Exception as e:
        return f"Gemini API error: {e}"

def save_history(feature, prompt, response):
    if "user_id" in session:
        con = db()
        con.execute("INSERT INTO history(user_id,feature,prompt,response) VALUES(?,?,?,?)",
                    (session["user_id"], feature, prompt, response))
        con.commit(); con.close()

@app.route("/")
def index():
    return render_template("index.html", user=session.get("name"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email=request.form["email"].strip().lower()
        password=request.form["password"]
        con=db(); user=con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone(); con.close()
        if user and check_password_hash(user["password"], password):
            session["user_id"]=user["id"]; session["name"]=user["name"]
            return redirect(url_for("index"))
        return render_template("login.html", error="Email அல்லது password தவறாக உள்ளது.")
    return render_template("login.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        name=request.form["name"].strip()
        email=request.form["email"].strip().lower()
        password=request.form["password"]
        try:
            con=db()
            con.execute("INSERT INTO users(name,email,password) VALUES(?,?,?)",
                        (name,email,generate_password_hash(password)))
            con.commit(); con.close()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return render_template("register.html", error="இந்த email ஏற்கனவே பயன்படுத்தப்பட்டுள்ளது.")
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/api/ask", methods=["POST"])
def ask():
    data=request.get_json() or {}
    question=data.get("question","").strip()
    if not question: return jsonify({"error":"Question உள்ளிடவும்."}),400
    prompt=f"""You are EduGenie, a helpful learning assistant for B.Sc Computer Science students.
Answer clearly and accurately. Use simple English unless the student asks for Tamil.
For programming questions, explain the code and include examples.
Student question: {question}"""
    answer=ai_generate(prompt)
    save_history("AI Chat", question, answer)
    return jsonify({"answer":answer})

@app.route("/api/generate", methods=["POST"])
def generate():
    data=request.get_json() or {}
    feature=data.get("feature","Notes")
    topic=data.get("topic","").strip()
    if not topic: return jsonify({"error":"Topic உள்ளிடவும்."}),400
    prompts={
        "Notes": f"Create well-structured study notes for B.Sc Computer Science students on '{topic}'. Include definition, key concepts, examples, advantages and a short summary.",
        "Quiz": f"Create 10 multiple-choice questions for B.Sc Computer Science students about '{topic}'. Give four options (A-D), the correct answer, and a one-line explanation.",
        "Summary": f"Give a concise student-friendly summary of '{topic}'. Cover only the most important concepts and key points.",
        "Coding": f"Teach '{topic}' to a B.Sc Computer Science student. Give a simple explanation, a working example program, line-by-line explanation, and expected output."
    }
    answer=ai_generate(prompts.get(feature, prompts["Notes"]))
    save_history(feature, topic, answer)
    return jsonify({"answer":answer})

@app.route("/history")
def history():
    if "user_id" not in session: return redirect(url_for("login"))
    con=db()
    rows=con.execute("SELECT * FROM history WHERE user_id=? ORDER BY id DESC LIMIT 50",(session["user_id"],)).fetchall()
    con.close()
    return render_template("history.html", rows=rows, user=session.get("name"))

init_db()
if __name__ == "__main__":
    app.run(debug=True)
