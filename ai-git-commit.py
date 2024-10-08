#!/usr/bin/env python3

import os
import subprocess
import json
import requests
from datetime import datetime
import time

# File paths
STARSHIP_LOGS = os.path.expanduser("~/.starship/logs")
CACHE_FILE = os.path.join(STARSHIP_LOGS, "ai-commit-cache")
FEEDBACK_LOG = os.path.join(STARSHIP_LOGS, "ai-commit-feedback.log")
LAST_RESPONSE_LOG = os.path.join(STARSHIP_LOGS, "last-openai-response.log")
REQUEST_LOG = os.path.join(STARSHIP_LOGS, "openai-request-payload.log")
API_KEY_PATH = os.path.expanduser("~/.ssh/openai-api-key")

# Available OpenAI models
MODEL_DESCRIPTIONS = {
    "gpt-3.5-turbo": "Fastest and most cost-effective model, good for most everyday tasks",
    "gpt-4": "More capable model, better for complex tasks and reasoning",
    "gpt-4-turbo": "Most advanced model, best for specialized and demanding applications"
}

DEFAULT_MODEL = "gpt-3.5-turbo"
MODEL = DEFAULT_MODEL

# Extract comments from the diff
def extract_comments_from_diff(diff_output):
    lines = diff_output.split("\n")
    comments = [line for line in lines if line.strip().startswith(("#", "//", "/*", "*/", "<!--", "--"))]
    if comments:
        print(f"Comments found: {' '.join(comments)}")
    else:
        print("No comments found in the diff.")
    return ' '.join(comments)

# Get the diff of staged changes
def get_diff():
    return subprocess.check_output(["git", "diff", "--staged"]).decode("utf-8")

# Verify if inside a Git repository
def is_git_repo():
    try:
        subprocess.check_output(["git", "rev-parse", "--is-inside-work-tree"])
        return True
    except subprocess.CalledProcessError:
        return False

# Check if there are staged changes
def has_staged_changes():
    try:
        subprocess.check_call(["git", "diff", "--staged", "--quiet"])
        return False
    except subprocess.CalledProcessError:
        return True

# Load the OpenAI API key
def load_api_key():
    try:
        with open(API_KEY_PATH, 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        print(f"Error: OpenAI API key not found at {API_KEY_PATH}.")
        return None

# Send request to OpenAI API
def send_request_to_openai(prompt, model):
    openai_api_key = load_api_key()
    if not openai_api_key:
        return None

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_api_key}"
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 200
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: OpenAI API request failed with status {response.status_code}")
        return None

# Log request payload
def log_request(prompt, model):
    with open(REQUEST_LOG, 'w') as log_file:
        log_file.write(f"Model: {model}\nPrompt: {prompt}\n")

# Log OpenAI response
def log_response(response):
    with open(LAST_RESPONSE_LOG, 'w') as log_file:
        log_file.write(json.dumps(response, indent=4))

# Get commit message suggestions

def get_commit_messages(diff_output, model):
    prompt = f"Generate 3 commit messages for the following git diff:\n{diff_output}\nProvide only the messages."
    log_request(prompt, model)

    response = send_request_to_openai(prompt, model)
    if response:
        log_response(response)
        commit_messages = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        return commit_messages.strip().split("\n")
    else:
        # More meaningful default messages based on the error
        if not diff_output.strip():
            return ["No changes to commit.", "Nothing modified.", "No staged changes."]
        else:
            return ["Failed to generate commit messages. Please try again.", "Unable to fetch AI suggestions."]


# Prompt user to select or customize a commit message
def prompt_commit_message(suggestions):
    while True:
        try:
            print("Prompting for commit message...")

            # Display available commit message suggestions
            for i, message in enumerate(suggestions, 1):
                print(f"{i}. {message}")
            print(f"{len(suggestions) + 1}. Enter custom message")

            # Prompt for user input
            choice = input("Choose a commit message (or enter number): ").strip()
            print(f"User input received: '{choice}'")

            if choice.isdigit():
                index = int(choice)
                if 1 <= index <= len(suggestions):
                    return suggestions[index - 1]

            elif choice == "":
                print("No input received. Please enter a valid choice.")
                continue  # Retry until valid input

            custom_message = input("Enter your custom commit message: ").strip()
            if custom_message:
                return custom_message
            else:
                print("Custom message cannot be empty.")
                continue

        except Exception as e:
            print(f"Error: {e}. Defaulting to fallback message.")
            return "Fallback: No input provided."

# Commit changes
def commit_changes(commit_message):
    subprocess.run(["git", "commit", "-m", commit_message])

# Cache commit message
def cache_commit_message(diff_output, commit_message):
    with open(CACHE_FILE, 'a') as cache:
        cache.write(f"{diff_output}|{commit_message}\n")

# Function to analyze feedback log
def analyze_feedback():
    if not os.path.exists(FEEDBACK_LOG):
        print(f"No feedback log found at {FEEDBACK_LOG}.")
        return

    with open(FEEDBACK_LOG, 'r') as feedback_file:
        feedback_data = feedback_file.read()

    prompt = f"Analyze the following feedback data:\n{feedback_data}\nProvide 3-5 suggestions to improve AI-generated commit messages."
    suggestions = send_request_to_openai(prompt, MODEL)
    if suggestions:
        print("Suggestions for improvement:")
        print(suggestions)

# Get commit status for Starship
def get_ai_commit_status():
    status_file = os.path.join(STARSHIP_LOGS, "ai-commit-status")
    if os.path.exists(status_file):
        with open(status_file, 'r') as file:
            last_used = int(file.read().strip())
        time_diff = int(datetime.now().timestamp()) - last_used

        if time_diff < 3600:
            return "🤖 Ready"
        elif time_diff < 86400:
            return f"🤖 {time_diff // 3600}h"
        else:
            return f"🤖 {time_diff // 86400}d"
    else:
        return "🤖 Not used"

# Main function to execute the AI git commit process
def ai_git_commit():
    if not is_git_repo():
        print("Error: Not inside a Git repository.")
        return

    if not has_staged_changes():
        print("No staged changes to commit.")
        return

    diff_output = get_diff()
    suggestions = get_commit_messages(diff_output, MODEL)

    if not suggestions:
        print("No commit message suggestions received from OpenAI.")
        return

    commit_message = prompt_commit_message(suggestions)
    commit_changes(commit_message)
    cache_commit_message(diff_output, commit_message)

# Alias for easy access
if __name__ == "__main__":
    ai_git_commit()
