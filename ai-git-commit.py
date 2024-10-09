import logging
import os
import subprocess
import time
from typing import List, Optional

import openai

# Configure logging
LOG_FOLDER = '/path/to/log/folder'
TIMESTAMP = time.strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(LOG_FOLDER, f"log_{TIMESTAMP}.txt")

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def get_staged_files() -> List[str]:
    try:
        result = subprocess.run(['git', 'diff', '--cached', '--name-only'],
                               capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n')
    except subprocess.CalledProcessError as e:
        logging.error(f"Error getting staged files: {e}")
        raise

def get_staged_changes_for_file(file_path: str) -> str:
    try:
        result = subprocess.run(['git', 'diff', '--cached', file_path],
                               capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Error getting changes for file {file_path}: {e}")
        return ""

def get_commit_message_suggestions(prompt: str) -> List[str]:
    # Initialize the OpenAI API client
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set in the environment variables")

    openai.api_key = api_key

    # Prepare the chat completion request
    messages = [
        {
            "role": "user",
            "content": prompt,
        }
    ]

    # Generate the completion
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens_per_prompt=2048,
            temperature=0.7,
            top_p=1,
            n=5,
        )

        # Extract the suggested messages
        suggestions = []
        for item in response['choices']:
            suggestions.append(item['delta'].strip())

        return suggestions

    except openai.OpenAIAPIException as e:
        logging.error(f"API request failed: {e}")
        return []  # Return an empty list if the API request fails

    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return []  # Return an empty list if any unexpected error occurs

def prompt_user_for_input(suggestions: List[str]) -> Optional[str]:
    print("\nAvailable commit message suggestions:")
    for i, suggestion in enumerate(suggestions):
        print(f"{i + 1}. {suggestion}")

    while True:
        choice = input("Enter the number of your preferred suggestion, or 'c' for custom: ")
        if choice.lower() == 'c':
            return None
        try:
            num = int(choice)
            if 1 <= num <= len(suggestions):
                return suggestions[num - 1]
            else:
                print("Invalid selection. Please choose a valid option.")
        except ValueError:
            print("Invalid input. Please enter a number or 'c'.")

def commit_file(file_path: str, message: str) -> None:
    """Commit a single file with the given message."""
    try:
        subprocess.run(['git', 'commit', '-m', f"{file_path}: {message}"], check=True)
        logging.info(f"Successfully committed file: {file_path}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to commit file {file_path}: {e}")

def main():
    # Check if triggered by auto-commit
    if 'GIT_COMMIT_SCRIPT_TRIGGERED' in os.environ:
        logging.info("Triggered by auto-commit feature")
    else:
        logging.info("Manual execution")

    try:
        staged_files = get_staged_files()
        if not staged_files:
            logging.warning("No staged files found. Exiting.")
            return

        logging.info(f"Found {len(staged_files)} staged files")

        print("\nStaged files:")
        for i, file in enumerate(staged_files):
            print(f"{i + 1}. {file}")

        selected_files = []
        custom_messages = {}

        for i, file in enumerate(staged_files, start=1):
            print(f"\nFile {i}: {file}")
            response = input("Do you want to commit this file? (y/n): ")
            if response.lower() == 'y':
                selected_files.append(i)

                prompt = f"""Here's a summary of the changes for {file}:

{get_staged_changes_for_file(file)}

Please provide a brief description of the changes."""

                suggestions = get_commit_message_suggestions(prompt)
                selected_message = prompt_user_for_input(suggestions)

                if selected_message is None:
                    selected_message = input(f"Please provide a custom commit message for {file}: ")

                custom_messages[file] = selected_message

        if not selected_files:
            logging.warning("No files selected for commit. Exiting.")
            return

        for file_index in selected_files:
            file = staged_files[file_index - 1]
            commit_file(file, custom_messages[file])
            logging.info(f"Successfully committed file: {file}")

        logging.info("All selected files committed successfully.")

    except Exception as e:
        logging.exception(f"An unexpected error occurred: {str(e)}")
        print(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()

