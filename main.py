from flask import Flask, render_template
from app import create_app

app = create_app()

@app.route("/")
def home():
    return render_template("base.html")  # or "index.html" if you want a different one