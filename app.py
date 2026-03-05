from selenium import webdriver
from selenium.common import NoSuchElementException, TimeoutException, ElementNotInteractableException # Import specific exceptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait, Select # Add Select import
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains # Add ActionChains import
from selenium.webdriver.common.keys import Keys # Add Keys import
from webdriver_manager.chrome import ChromeDriverManager
import time
import traceback
import re
import os
import json # Import json module
import requests # Import requests module
from rag_system import MilvusRAGSystem # Import RAG system

# --- Configuration ---
# OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_API_KEY = "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"
LLM_MODEL = "openai/gpt-oss-120b"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
WAIT_TIMEOUT = 10 # Seconds to wait for elements
DROPDOWN_WAIT_TIMEOUT = 15 # Longer timeout for dropdown operations
SHORT_DELAY = 2 # Seconds delay after action
MAX_CREDENTIAL_ATTEMPTS = 3 # Maximum attempts to get credentials from user
MAX_DECISION_ATTEMPTS = 3 # Maximum attempts to get user decisions

# Initialize RAG system (will be initialized in main)
rag_system = None

# --- Generic Decision Making System ---
def prompt_user_decision(context: str, question: str, options: list = None, decision_type: str = "choice") -> str:
    """
    Generic function to prompt user for decisions with retry logic.
    
    Args:
        context: Background information about the current situation
        question: The specific question/decision to ask
        options: List of available options (if applicable)
        decision_type: Type of decision ("choice", "text_input", "yes_no")
    
    Returns:
        User's decision as a string, or None if failed
    """
    print(f"\n{'='*60}")
    print("HUMAN DECISION REQUIRED")
    print(f"{'='*60}")
    print(f"Context: {context}")
    print(f"\nQuestion: {question}")
    
    if options and decision_type == "choice":
        print(f"\nAvailable options:")
        for i, option in enumerate(options, 1):
            print(f"  {i}. {option}")
    
    attempts = 0
    while attempts < MAX_DECISION_ATTEMPTS:
        try:
            if decision_type == "choice" and options:
                response = input(f"\nPlease select an option (1-{len(options)}) or type your custom response (attempt {attempts + 1}/{MAX_DECISION_ATTEMPTS}): ").strip()
                
                # Check if it's a number selection
                if response.isdigit():
                    choice_num = int(response)
                    if 1 <= choice_num <= len(options):
                        selected_option = options[choice_num - 1]
                        print(f"You selected: {selected_option}")
                        return selected_option
                    else:
                        print(f"Invalid option number. Please choose between 1 and {len(options)}.")
                        attempts += 1
                        continue
                
                # If not a number, treat as custom response
                if response:
                    print(f"You entered: {response}")
                    return response
                else:
                    print("Response cannot be empty.")
                    
            elif decision_type == "yes_no":
                response = input(f"\nPlease answer yes/no (attempt {attempts + 1}/{MAX_DECISION_ATTEMPTS}): ").strip().lower()
                if response in ['yes', 'y', 'no', 'n']:
                    result = 'yes' if response in ['yes', 'y'] else 'no'
                    print(f"You answered: {result}")
                    return result
                else:
                    print("Please answer with 'yes' or 'no'.")
                    
            else:  # text_input or fallback
                response = input(f"\nPlease provide your input (attempt {attempts + 1}/{MAX_DECISION_ATTEMPTS}): ").strip()
                if response:
                    print(f"You entered: {response}")
                    return response
                else:
                    print("Input cannot be empty.")
            
            attempts += 1
            
        except KeyboardInterrupt:
            print("\nDecision input cancelled by user.")
            return None
        except Exception as e:
            print(f"Error getting decision: {e}")
            attempts += 1
    
    print(f"Failed to get a valid decision after {MAX_DECISION_ATTEMPTS} attempts.")
    return None

def parse_human_decision_step(step_description: str) -> dict:
    """
    Parse a human decision step to extract the question and options.
    Expected format: "HUMAN_DECISION: context | question | option1,option2,option3"
    """
    if not step_description.upper().startswith("HUMAN_DECISION:"):
        return None
    
    try:
        # Remove the prefix
        content = step_description[len("HUMAN_DECISION:"):].strip()
        parts = content.split("|")
        
        if len(parts) >= 2:
            context = parts[0].strip()
            question = parts[1].strip()
            options = []
            decision_type = "text_input"
            
            if len(parts) >= 3:
                options_str = parts[2].strip()
                if options_str.lower() == "yes_no":
                    decision_type = "yes_no"
                elif options_str:
                    options = [opt.strip() for opt in options_str.split(",") if opt.strip()]
                    decision_type = "choice" if options else "text_input"
            
            return {
                "context": context,
                "question": question,
                "options": options,
                "decision_type": decision_type
            }
    except Exception as e:
        print(f"Error parsing human decision step: {e}")
    
    return None

# --- Credential Management ---
def is_authentication_error(error_message: str, html_content: str = "") -> bool:
    """
    Detect if an error message or HTML content indicates authentication failure.
    Returns True if the error appears to be related to wrong credentials.
    """
    if not error_message and not html_content:
        return False
    
    # Check error message for authentication-related keywords
    auth_error_keywords = [
        'invalid credentials', 'wrong password', 'incorrect password',
        'invalid username', 'invalid email', 'authentication failed',
        'login failed', 'access denied', 'unauthorized', 'invalid login',
        'wrong username', 'incorrect email', 'bad credentials',
        'authentication error', 'login error', 'credential error',
        'password incorrect', 'username not found', 'email not found'
    ]
    
    error_lower = error_message.lower() if error_message else ""
    html_lower = html_content.lower() if html_content else ""
    
    # Check if error message contains authentication keywords
    for keyword in auth_error_keywords:
        if keyword in error_lower:
            return True
    
    # Check HTML content for common error messages
    html_error_indicators = [
        'invalid credentials', 'wrong password', 'incorrect password',
        'login failed', 'authentication failed', 'access denied',
        'error-message', 'login-error', 'auth-error', 'credential-error',
        'password is incorrect', 'username is invalid', 'email is invalid'
    ]
    
    for indicator in html_error_indicators:
        if indicator in html_lower:
            return True
    
    return False

def re_prompt_credentials(reason: str = "") -> dict:
    """
    Re-prompt user for credentials with context about why re-prompting is needed.
    """
    print(f"\n{'='*70}")
    print("CREDENTIAL RE-ENTRY REQUIRED")
    print(f"{'='*70}")
    
    if reason:
        print(f"Reason: {reason}")
    else:
        print("Reason: Previous credentials appear to be incorrect or authentication failed.")
    
    print("\nPlease re-enter your credentials:")
    
    # Always ask for both username and password when re-prompting
    return prompt_for_credentials(['username/email', 'password'])

def needs_credentials(user_goal: str, html_content: str = "") -> dict:
    """
    Detect if the user goal requires credentials that are missing.
    Returns a dict with 'needs_username', 'needs_password', and 'missing_credentials' keys.
    """
    goal_lower = user_goal.lower()
    needs_creds = {
        'needs_username': False,
        'needs_password': False,
        'missing_credentials': []
    }
    
    # Check if goal mentions login/authentication
    login_keywords = ['login', 'log in', 'sign in', 'authenticate', 'auth']
    mentions_login = any(keyword in goal_lower for keyword in login_keywords)
    
    if mentions_login:
        # Check for existing credentials in the goal
        has_username = any(pattern in goal_lower for pattern in [
            'username is', 'user is', 'email is', 'my username', 'my email',
            '@', 'username:', 'email:', 'user:'
        ])
        
        has_password = any(pattern in goal_lower for pattern in [
            'password is', 'my password', 'password:', 'pass is'
        ])
        
        if not has_username:
            needs_creds['needs_username'] = True
            needs_creds['missing_credentials'].append('username/email')
            
        if not has_password:
            needs_creds['needs_password'] = True
            needs_creds['missing_credentials'].append('password')
    
    # Additional check: look for login forms in HTML
    if html_content:
        html_lower = html_content.lower()
        has_login_form = any(pattern in html_lower for pattern in [
            'type="password"', 'name="password"', 'id="password"',
            'type="email"', 'name="email"', 'name="username"',
            'login-form', 'signin-form', 'auth-form'
        ])
        
        if has_login_form and not mentions_login:
            # If there's a login form but user didn't mention login, 
            # we might still need credentials
            needs_creds['needs_username'] = True
            needs_creds['needs_password'] = True
            needs_creds['missing_credentials'] = ['username/email', 'password']
    
    return needs_creds

def prompt_for_credentials(missing_credentials: list) -> dict:
    """
    Prompt user for missing credentials with retry logic.
    Returns a dict with the collected credentials or None if failed.
    """
    credentials = {}
    
    for credential_type in missing_credentials:
        attempts = 0
        while attempts < MAX_CREDENTIAL_ATTEMPTS:
            try:
                if credential_type == 'username/email':
                    value = input(f"\nPlease enter your username or email (attempt {attempts + 1}/{MAX_CREDENTIAL_ATTEMPTS}): ").strip()
                    if value:
                        credentials['username'] = value
                        break
                    else:
                        print("Username/email cannot be empty.")
                        
                elif credential_type == 'password':
                    import getpass
                    value = getpass.getpass(f"\nPlease enter your password (attempt {attempts + 1}/{MAX_CREDENTIAL_ATTEMPTS}): ").strip()
                    if value:
                        credentials['password'] = value
                        break
                    else:
                        print("Password cannot be empty.")
                        
                attempts += 1
                
            except KeyboardInterrupt:
                print("\nCredential input cancelled by user.")
                return None
            except Exception as e:
                print(f"Error getting {credential_type}: {e}")
                attempts += 1
        
        if attempts >= MAX_CREDENTIAL_ATTEMPTS:
            print(f"Failed to get {credential_type} after {MAX_CREDENTIAL_ATTEMPTS} attempts.")
            return None
    
    return credentials

def update_goal_with_credentials(user_goal: str, credentials: dict) -> str:
    """
    Update the user goal to include the provided credentials.
    This function now also removes old credentials if they exist.
    """
    # First, remove any existing credential information from the goal
    goal_lower = user_goal.lower()
    
    # Patterns to identify and remove existing credentials
    credential_patterns = [
        r'my username is [^\s]+',
        r'my email is [^\s]+', 
        r'my password is [^\s]+',
        r'username is [^\s]+',
        r'email is [^\s]+',
        r'password is [^\s]+',
        r'my username [^\s]+',
        r'my email [^\s]+',
        r'my password [^\s]+',
    ]
    
    updated_goal = user_goal
    
    # Remove existing credentials from the goal
    for pattern in credential_patterns:
        updated_goal = re.sub(pattern, '', updated_goal, flags=re.IGNORECASE)
    
    # Clean up any double spaces or trailing spaces
    updated_goal = re.sub(r'\s+', ' ', updated_goal).strip()
    
    # Add new credentials to the beginning of the goal
    credential_text = ""
    if 'username' in credentials:
        credential_text += f"My username is {credentials['username']}"
    if 'password' in credentials:
        if credential_text:
            credential_text += f" and password is {credentials['password']}. "
        else:
            credential_text += f"My password is {credentials['password']}. "
    
    if credential_text:
        updated_goal = credential_text + updated_goal
    
    return updated_goal

# --- Selenium Setup ---
def setup_driver():
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    # options.add_argument('--disable-gpu')
    
    try:
        # Try to use ChromeDriverManager
        driver_path = ChromeDriverManager().install()
        
        # Check if the path points to the actual chromedriver executable
        import os
        if not os.path.isfile(driver_path) or not os.access(driver_path, os.X_OK):
            # If the path is wrong, try to find the actual chromedriver
            driver_dir = os.path.dirname(driver_path)
            for file in os.listdir(driver_dir):
                if file == 'chromedriver' and os.access(os.path.join(driver_dir, file), os.X_OK):
                    driver_path = os.path.join(driver_dir, file)
                    break
        
        driver = webdriver.Chrome(service=Service(driver_path), options=options)
    except Exception as e:
        print(f"Error with ChromeDriverManager: {e}")
        print("Trying to use system chromedriver...")
        # Fallback to system chromedriver
        try:
            driver = webdriver.Chrome(options=options)
        except Exception as e2:
            print(f"Error with system chromedriver: {e2}")
            raise Exception("Could not initialize Chrome driver. Please ensure Chrome and chromedriver are properly installed.")
    
    return driver

# --- Enhanced LLM Interaction with RAG ---
def get_rag_context(user_goal: str) -> str:
    """Get relevant context from RAG system based on user goal"""
    global rag_system
    
    if rag_system is None:
        return ""
    
    try:
        # Extract potential documentation queries from the user goal
        doc_queries = []
        
        # Look for keywords that might benefit from documentation
        keywords = ['login', 'authentication', 'pricing', 'api', 'security', 'features', 'setup', 'configuration']
        for keyword in keywords:
            if keyword.lower() in user_goal.lower():
                doc_queries.append(f"How to {keyword}")
        
        # If no specific keywords found, use the goal itself
        if not doc_queries:
            doc_queries = [user_goal]
        
        # Get RAG context for the most relevant query
        rag_result = rag_system.query(doc_queries[0], top_k=3)
        
        if rag_result['retrieved_docs']:
            context = "\n".join([
                f"Documentation: {doc['text'][:500]}..."
                for doc in rag_result['retrieved_docs'][:2]  # Use top 2 results
            ])
            return f"\n\nRelevant Documentation Context:\n{context}\n"
        
    except Exception as e:
        print(f"--- Error getting RAG context: {e} ---")
    
    return ""

# --- LLM Interaction ---
def get_llm_web_steps(driver, user_goal, completed_steps_context: list[str], previous_error_info: str | None = None):
    print(f"\n--- Requesting LLM to generate web operation steps for goal: \"{user_goal[:80]}...\" ---")
    if previous_error_info:
        print(f"--- Context from previous step generation/execution attempt: {previous_error_info} ---")

    # Get RAG context for enhanced understanding
    rag_context = get_rag_context(user_goal)

    html_content = driver.page_source
    MAX_HTML_LEN = 1000000 # Approx 100KB
    if len(html_content) > MAX_HTML_LEN:
        print(f"--- Truncating HTML content from {len(html_content)} to {MAX_HTML_LEN} chars for LLM prompt ---")
        html_content = html_content[:MAX_HTML_LEN] + "\n... (HTML truncated) ..."

    completed_steps_str = "\n".join([f"- {s}" for s in completed_steps_context]) if completed_steps_context else "None yet."

    json_steps_example = '''
    [
      {"description": "Type the email 'user@example.com' into the email input field."},
      {"description": "Type the password 'securepassword123' into the password input field."},
      {"description": "Click the main login button."},
      {"description": "wait for 3 seconds"},
      {"description": "HUMAN_DECISION: Multiple projects available | Which project should I select? | ProjectA,ProjectB,ProjectC"}
    ]
    '''

    prompt = f"""
You are an AI assistant driving a web browser based on a user's high-level goal and the current page's HTML.
Your task is to generate a short, logical sequence of 1 to 3 user-facing actions to perform next.

User's Overall Goal:
{user_goal}
{rag_context}
Current HTML Content of the Webpage (may be truncated):
---
{html_content}
---

Previously Completed Steps in this Session:
---
{completed_steps_str}
---
"""
    if previous_error_info:
        prompt += f"""
The previous attempt to generate or execute steps resulted in an error:
---
{previous_error_info}
---

CRITICAL INSTRUCTIONS FOR STEP REGENERATION:
1. The previous approach failed - you MUST try a completely different strategy
2. If the error shows available data-test-id values, use those exact values in your selectors
3. For dropdown selection tasks that failed:
   - Break it into multiple steps: first open dropdown, then select option
   - Use the exact data-test-id values shown in the error context
   - Try different action types: 'hover', 'click', then 'click_dropdown_option'
4. If specific selectors failed, generate steps that use different selector strategies
5. Pay attention to the visible elements information to understand what's actually on the page
6. Consider that the dropdown might need time to load or animate - add wait steps if needed

Generate a completely new approach based on the error context and available elements shown above.
"""
    prompt += f"""
Instructions for your response:
1.  Examine the HTML and the user's goal.
2.  If the goal involves typing information (like usernames, passwords, search terms), and relevant input fields are visible, your steps should include typing that information. Embed the actual values to type directly in the description string.
3.  If the goal involves waiting, include a step like: {{"description": "wait for X seconds"}}.
4.  **IMPORTANT: If you encounter ANY situation where human decision/input is needed, create a HUMAN_DECISION step using this format:**
    {{"description": "HUMAN_DECISION: [context] | [question] | [options_or_type]"}}
    
    Examples of when to request human decisions:
    - Multiple similar elements/options available (e.g., multiple buttons, links, dropdown options)
    - Ambiguous user goal that could be interpreted multiple ways
    - Form fields that require user-specific information not provided in the goal
    - Confirmation needed before potentially destructive actions
    - When you're uncertain about which path to take
    
    Format for HUMAN_DECISION:
    - Context: Brief description of the current situation
    - Question: Clear question asking what the user wants to do
    - Options: Either comma-separated list of choices, "yes_no" for yes/no questions, or leave empty for free text input
    
    Example: "HUMAN_DECISION: Found 3 different login buttons on the page | Which login method do you prefer? | Google Login,Email Login,SSO Login"
    
5.  Respond ONLY with a single JSON list of objects. Each object MUST have a "description" key, containing a natural language string of the action.
6.  If you believe the user's goal (or the current relevant part of it) is complete, or if no sensible next actions can be determined from the current page and goal, return an empty JSON list: [].

Example of a valid JSON response format:
{json_steps_example}

Based on the above, provide the JSON list of step descriptions:
"""
    json_string = None
    try:
        if not OPENROUTER_API_KEY:
            print("--- Error: OPENROUTER_API_KEY is not set. ---")
            return None
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=data, timeout=45)
        response.raise_for_status()
        raw_response_json = response.json()

        if raw_response_json.get("choices") and raw_response_json["choices"][0].get("message"):
            json_string = raw_response_json["choices"][0]["message"].get("content")
            if not json_string:
                print("--- Error: Empty content in OpenRouter response. ---")
                return None
            json_string = json_string.strip()
            if json_string.startswith("```"):
                json_string = json_string.strip("`")
                json_string = json_string.replace("json", "", 1).strip()
            print(f"--- Extracted JSON String for steps ---\n{json_string}\n---------------------------")
            parsed_steps = json.loads(json_string)
            if not isinstance(parsed_steps, list):
                print("--- Error: Parsed JSON for steps is not a list. ---")
                return None
            for step in parsed_steps:
                if not isinstance(step, dict) or "description" not in step:
                    print(f"--- Error: Invalid step format in list: {step}. Missing 'description'. ---")
                    return None
            print(f"--- Parsed Step Descriptions ---\n{json.dumps(parsed_steps, indent=2)}\n--------------------------")
            return parsed_steps
        else:
            print("--- Error: Could not find JSON content for steps in OpenRouter response. ---")
            print(f"--- Raw Response: {json.dumps(raw_response_json, indent=2)} ---")
            return None
    except requests.exceptions.HTTPError as http_err:
        print(f"--- HTTP error in get_llm_web_steps: {http_err} - {response.text} ---")
        return None
    except requests.exceptions.RequestException as req_err:
        print(f"--- Request error in get_llm_web_steps: {req_err} ---")
        return None
    except json.JSONDecodeError as jde:
        print(f"--- Error: Failed to decode JSON string for steps: {jde} ---")
        print(f"Extracted string was: {json_string}")
        return None
    except Exception as e:
        print(f"--- Error during OpenRouter API call or JSON processing in get_llm_web_steps: {e} ---")
        print(traceback.format_exc())
        return None

def get_llm_instruction(driver, step_description, previous_error: str | None = None):
    print(f"\n--- Requesting Instruction for Step: {step_description[:60]}... ---")
    if previous_error:
        print(f"--- Previous attempt failed with error: {previous_error} ---")
    html_content = driver.page_source
    MAX_HTML_LEN = 1000000 # Unify with get_llm_web_steps
    if len(html_content) > MAX_HTML_LEN:
        print(f"--- Truncating HTML content from {len(html_content)} to {MAX_HTML_LEN} chars for LLM prompt ---")
        html_content = html_content[:MAX_HTML_LEN] + "\n... (HTML truncated) ..."
    json_example = '''
    {
      "action": "type|click|scroll_to_element|select_dropdown|click_dropdown_option|hover",
      "selector_type": "css|xpath",
      "selector": "<Your CSS or XPath selector here>",
      "value": "<Text to type (for 'type'), option text/value (for 'select_dropdown'), or option selector (for 'click_dropdown_option')>",
      "option_selector": "<Optional: CSS/XPath selector for dropdown option (for 'click_dropdown_option')>"
    }
    '''
    # Get dropdown-specific guidance
    dropdown_guidance = detect_dropdown_type(html_content, step_description)
    
    prompt = f"""
Given the current HTML content of the webpage, provide a JSON object specifying the Selenium action needed to perform the following task.

Task:
{step_description}

HTML Content Snippet (may be truncated):
---
{html_content}
---
{dropdown_guidance}

Respond ONLY with a single JSON object in the following format (do not include ```json markers or any other text):
{json_example}

Choose the simplest and most reliable selector (CSS preferably, XPath if necessary).
Ensure the 'action' is one of: 'click', 'type', 'scroll_to_element', 'select_dropdown', 'click_dropdown_option', or 'hover'.

Action-specific requirements:
- 'type': 'value' key MUST contain the text to type
- 'select_dropdown': Use for HTML <select> elements. 'value' should contain the option text or value to select
- 'click_dropdown_option': Use for custom dropdowns. 'value' should contain option text, 'option_selector' can contain specific option selector
- 'hover': Use to hover over elements (useful for dropdown triggers)

For dropdown selection tasks:
- If you see a <select> element, use 'select_dropdown' action
- If you see a custom dropdown (div-based), use 'click' to open it, then 'click_dropdown_option' to select an option
- Consider using 'hover' if dropdown appears on hover
"""
    if previous_error:
        prompt += f"""
The previous attempt to execute an action for this step failed with the following error:
---
{previous_error}
---

IMPORTANT INSTRUCTIONS FOR RETRY:
1. Analyze the error details and available elements listed above
2. If the error mentions a specific selector that failed, try a different approach:
   - For data-test-id selectors that failed, try CSS selector format: [data-test-id="value"]
   - For dropdown options, try different element types (li, div, a, span)
   - Consider if the dropdown needs to be opened first with a separate click action
3. Use the "Available data-test-id values" list to find the correct selector
4. If this is a dropdown selection task and the previous attempt failed:
   - First try 'click' action to open the dropdown
   - Then use 'click_dropdown_option' with the correct option selector
   - Or use 'select_dropdown' if it's an HTML <select> element
5. Look at the visible elements information to understand the page structure

Please provide a completely different approach than the previous failed attempt. If the previous attempt used XPath, try CSS selectors. If it used 'click', try 'click_dropdown_option' or 'hover' first.
"""
    prompt += """
JSON Instruction:
"""
    instruction = None
    json_string = None
    try:
        if not OPENROUTER_API_KEY:
            print("--- Error: OPENROUTER_API_KEY is not set. ---")
            return None
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }

        response = requests.post(OPENROUTER_API_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()

        raw_response_json = response.json()
        # print(f"--- Raw OpenRouter API Response ---\n{json.dumps(raw_response_json, indent=2)}\n------------------------")

        if raw_response_json.get("choices") and raw_response_json["choices"][0].get("message"):
            json_string = raw_response_json["choices"][0]["message"].get("content")
            if not json_string:
                print("--- Error: Empty content in OpenRouter response. ---")
                return None
            json_string = json_string.strip()
            if json_string.startswith("```"):
                json_string = json_string.strip("`")
                json_string = json_string.replace("json", "", 1).strip()
            # print(f"--- Extracted JSON String ---\n{json_string}\n---------------------------")
            instruction = json.loads(json_string)

            if not all(k in instruction for k in ['action', 'selector_type', 'selector']):
                print("--- Error: Parsed JSON missing required keys (action, selector_type, selector). ---")
                instruction = None
            elif instruction['action'] in ['type', 'select_dropdown', 'click_dropdown_option'] and 'value' not in instruction:
                 print(f"--- Error: OpenRouter response for '{instruction['action']}' action from description '{step_description[:50]}' missing 'value'. ---")
                 instruction = None
            elif instruction['selector_type'] not in ['css', 'xpath']:
                 print("--- Error: Parsed JSON has invalid 'selector_type'. ---")
                 instruction = None
        else:
            print("--- Error: Could not find JSON content in OpenRouter response. ---")
            # print(f"--- Raw Response: {json.dumps(raw_response_json, indent=2)} ---")


        if instruction:
             print(f"--- Parsed Instruction ---\n{json.dumps(instruction, indent=2)}\n--------------------------")

        return instruction

    except requests.exceptions.HTTPError as http_err:
        print(f"--- HTTP error occurred: {http_err} - {response.text} ---")
        return None
    except requests.exceptions.RequestException as req_err:
        print(f"--- Request error occurred: {req_err} ---")
        return None
    except json.JSONDecodeError as jde:
        print(f"--- Error: Failed to decode extracted JSON string: {jde} ---")
        print(f"Extracted string was: {json_string}")
        return None
    except Exception as e:
        print(f"--- Error during OpenRouter API call or JSON processing: {e} ---")
        print(traceback.format_exc())
        return None

# --- Dropdown Detection Helper ---
def capture_dropdown_debug_info(driver, failed_selector: str = None) -> str:
    """
    Capture detailed debugging information about dropdown state when selection fails.
    """
    debug_info = []
    
    try:
        # Get all potentially relevant elements
        debug_info.append("=== DROPDOWN DEBUG INFORMATION ===")
        
        # Check for common dropdown patterns
        dropdown_patterns = [
            ("Buttons with dropdown classes", "//button[contains(@class, 'dropdown') or contains(@class, 'select')]"),
            ("Elements with data-test-id", "//*[@data-test-id]"),
            ("List items", "//li"),
            ("Dropdown menus", "//*[contains(@class, 'menu') or contains(@class, 'dropdown')]"),
            ("Role-based options", "//*[@role='option' or @role='listbox' or @role='menu']"),
            ("Clickable elements with text", "//*[contains(text(), '24') or contains(text(), 'hour') or contains(text(), 'day')]")
        ]
        
        for pattern_name, xpath in dropdown_patterns:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                visible_elements = [elem for elem in elements if elem.is_displayed()]
                
                if visible_elements:
                    debug_info.append(f"\n{pattern_name} ({len(visible_elements)} visible):")
                    for i, elem in enumerate(visible_elements[:5]):  # Show first 5
                        try:
                            text = elem.text[:30] if elem.text else "No text"
                            class_attr = elem.get_attribute('class') or "No class"
                            test_id = elem.get_attribute('data-test-id') or "No test-id"
                            debug_info.append(f"  {i+1}. {elem.tag_name}: '{text}' | class='{class_attr}' | data-test-id='{test_id}'")
                        except:
                            debug_info.append(f"  {i+1}. {elem.tag_name}: Error getting attributes")
            except Exception as e:
                debug_info.append(f"{pattern_name}: Error - {e}")
        
        # If a specific selector failed, try to understand why
        if failed_selector:
            debug_info.append(f"\n=== ANALYSIS OF FAILED SELECTOR: {failed_selector} ===")
            try:
                # Try to find similar elements
                if 'data-test-id' in failed_selector:
                    test_id_value = failed_selector.split('"')[1] if '"' in failed_selector else failed_selector.split("'")[1]
                    similar_selectors = [
                        f"[data-test-id='{test_id_value}']",
                        f"//*[@data-test-id='{test_id_value}']",
                        f"//li[@data-test-id='{test_id_value}']",
                        f"//div[@data-test-id='{test_id_value}']",
                        f"//a[@data-test-id='{test_id_value}']"
                    ]
                    
                    for selector in similar_selectors:
                        try:
                            by_strategy = By.CSS_SELECTOR if not selector.startswith('//') else By.XPATH
                            elements = driver.find_elements(by_strategy, selector)
                            if elements:
                                debug_info.append(f"  Alternative selector '{selector}' found {len(elements)} elements")
                                for elem in elements[:2]:
                                    debug_info.append(f"    - Visible: {elem.is_displayed()}, Text: '{elem.text[:20]}'")
                            else:
                                debug_info.append(f"  Alternative selector '{selector}' found 0 elements")
                        except Exception as e:
                            debug_info.append(f"  Alternative selector '{selector}' error: {e}")
            except:
                pass
        
        # Check page state
        debug_info.append(f"\n=== PAGE STATE ===")
        debug_info.append(f"URL: {driver.current_url}")
        debug_info.append(f"Title: {driver.title}")
        
        return "\n".join(debug_info)
        
    except Exception as e:
        return f"Error capturing dropdown debug info: {e}"

def detect_dropdown_type(html_content: str, step_description: str) -> str:
    """
    Analyze HTML content and step description to provide dropdown handling guidance.
    Returns guidance string for the LLM.
    """
    guidance = ""
    
    # Check for HTML select elements
    if '<select' in html_content.lower():
        guidance += "\nDROPDOWN GUIDANCE: HTML <select> elements detected. Use 'select_dropdown' action for these.\n"
    
    # Check for common custom dropdown patterns
    custom_dropdown_indicators = [
        'dropdown', 'select', 'combobox', 'listbox', 'menu',
        'role="listbox"', 'role="combobox"', 'role="menu"',
        'data-toggle="dropdown"', 'aria-haspopup="true"'
    ]
    
    for indicator in custom_dropdown_indicators:
        if indicator in html_content.lower():
            guidance += f"\nDROPDOWN GUIDANCE: Custom dropdown patterns detected ('{indicator}'). Consider using 'click' to open, then 'click_dropdown_option' to select.\n"
            break
    
    # Check if step mentions dropdown selection
    dropdown_keywords = ['select', 'choose', 'pick', 'dropdown', 'option']
    if any(keyword in step_description.lower() for keyword in dropdown_keywords):
        guidance += "\nDROPDOWN GUIDANCE: This appears to be a dropdown selection task. Look for <select> elements or clickable dropdown triggers.\n"
    
    return guidance

def handle_dropdown_with_retry(driver, element, value, option_selector=None, max_retries=3):
    """
    Handle dropdown selection with retry logic for common issues.
    """
    for attempt in range(max_retries):
        try:
            print(f"Dropdown selection attempt {attempt + 1}/{max_retries}")
            
            # Scroll element into view
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.5)
            
            # Check if dropdown is already open
            dropdown_already_open = False
            try:
                existing_options = driver.find_elements(By.XPATH, "//li[contains(@class, 'option')] | //div[@role='option'] | //*[contains(@data-test-id, '24h') or contains(@data-test-id, '7d') or contains(@data-test-id, '30d')]")
                if existing_options and any(opt.is_displayed() for opt in existing_options):
                    print("Dropdown appears to already be open")
                    dropdown_already_open = True
            except:
                pass
            
            # Try to click to open dropdown (unless already open)
            if not dropdown_already_open:
                try:
                    element.click()
                    print("Clicked dropdown to open it.")
                except Exception as click_error:
                    print(f"Direct click failed, trying JavaScript click: {click_error}")
                    driver.execute_script("arguments[0].click();", element)
                    print("Used JavaScript click on dropdown.")
            else:
                print("Skipping dropdown click since it appears to already be open")
            
            # Wait for dropdown to open and populate with progressive checking
            max_wait_time = 5
            wait_increment = 0.5
            total_waited = 0
            
            while total_waited < max_wait_time:
                time.sleep(wait_increment)
                total_waited += wait_increment
                
                # Check if dropdown options are now visible
                try:
                    visible_options = driver.find_elements(By.XPATH, "//li[contains(@style, 'display: block')] | //div[@role='option'] | //*[contains(@class, 'option') and not(contains(@style, 'display: none'))]")
                    if visible_options:
                        print(f"Dropdown options became visible after {total_waited} seconds")
                        break
                except:
                    pass
            
            print(f"Waited {total_waited} seconds for dropdown to populate")
            
            # Now find and click the option
            if option_selector:
                # Use specific option selector if provided
                option_by_strategy = By.CSS_SELECTOR if option_selector.startswith('.') or option_selector.startswith('#') or not option_selector.startswith('//') else By.XPATH
                option_wait = WebDriverWait(driver, 8)  # Increased timeout for specific selectors
                
                try:
                    print(f"Looking for option with selector: {option_selector}")
                    option_element = option_wait.until(EC.element_to_be_clickable((option_by_strategy, option_selector)))
                    option_element.click()
                    print(f"Clicked dropdown option using selector: '{option_selector}'")
                    return True
                except TimeoutException:
                    print(f"Specific selector '{option_selector}' timed out, trying alternative approaches...")
                    
                    # If the specific selector fails, try to find it by data-test-id in different ways
                    if 'data-test-id' in option_selector:
                        test_id = option_selector.split('"')[1] if '"' in option_selector else option_selector.split("'")[1]
                        alternative_selectors = [
                            f"[data-test-id='{test_id}']",
                            f"*[data-test-id='{test_id}']",
                            f"//*[@data-test-id='{test_id}']",
                            f"//li[@data-test-id='{test_id}']",
                            f"//div[@data-test-id='{test_id}']",
                            f"//a[@data-test-id='{test_id}']"
                        ]
                        
                        for alt_selector in alternative_selectors:
                            try:
                                alt_by_strategy = By.CSS_SELECTOR if not alt_selector.startswith('//') else By.XPATH
                                alt_element = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((alt_by_strategy, alt_selector)))
                                alt_element.click()
                                print(f"Clicked dropdown option using alternative selector: '{alt_selector}'")
                                return True
                            except:
                                continue
                    
                    # If all specific selectors fail, fall through to text-based search
                    print("All specific selectors failed, falling back to text-based search")
            
            # Try to find option by text content with multiple strategies (for both cases)
            option_found = False
            option_wait = WebDriverWait(driver, 5)
            
            # Enhanced option patterns with more specificity
            option_patterns = [
                f"//li[normalize-space(text())='{value}']",
                f"//div[normalize-space(text())='{value}']",
                f"//span[normalize-space(text())='{value}']",
                f"//option[normalize-space(text())='{value}']",
                f"//*[@role='option'][normalize-space(text())='{value}']",
                f"//li[contains(normalize-space(text()), '{value}')]",
                f"//div[contains(normalize-space(text()), '{value}')]",
                f"//span[contains(normalize-space(text()), '{value}')]",
                f"//*[@role='option'][contains(normalize-space(text()), '{value}')]",
                f"//li[contains(@class, 'option')][contains(normalize-space(text()), '{value}')]",
                f"//div[contains(@class, 'option')][contains(normalize-space(text()), '{value}')]",
                f"//a[contains(normalize-space(text()), '{value}')]",
                f"//*[contains(@data-value, '{value}')]"
            ]
            
            for pattern in option_patterns:
                try:
                    print(f"Trying pattern: {pattern}")
                    option_element = option_wait.until(EC.element_to_be_clickable((By.XPATH, pattern)))
                    # Scroll option into view if needed
                    driver.execute_script("arguments[0].scrollIntoView({block: 'nearest'});", option_element)
                    time.sleep(0.2)
                    option_element.click()
                    print(f"Clicked dropdown option: '{value}' using pattern: {pattern}")
                    option_found = True
                    return True
                except TimeoutException:
                    print(f"Pattern {pattern} timed out")
                    continue
                except Exception as option_error:
                    print(f"Error clicking option with pattern {pattern}: {option_error}")
                    continue
            
            if not option_found:
                # Try to get available options for debugging
                try:
                    print("Attempting to find available dropdown options...")
                    # Try multiple selectors to find dropdown options
                    option_selectors = [
                        "//li",
                        "//div[@role='option']", 
                        "//*[contains(@class, 'option')]",
                        "//a[contains(@class, 'dropdown')]",
                        "//*[contains(@data-test-id, '')]",
                        "//ul//li",
                        "//div[contains(@class, 'dropdown')]//div",
                        "//div[contains(@class, 'menu')]//div"
                    ]
                    
                    all_options = []
                    for selector in option_selectors:
                        try:
                            elements = driver.find_elements(By.XPATH, selector)
                            for elem in elements:
                                if elem.is_displayed() and elem.text.strip():
                                    all_options.append(f"{elem.text.strip()} (tag: {elem.tag_name}, class: {elem.get_attribute('class')}, data-test-id: {elem.get_attribute('data-test-id')})")
                        except:
                            continue
                    
                    if all_options:
                        print(f"Available visible options found: {all_options[:15]}")  # Show first 15
                    else:
                        print("No visible dropdown options found")
                        
                    # Also try to get the current page source around dropdown area
                    try:
                        dropdown_area = driver.find_element(By.TAG_NAME, "body")
                        dropdown_html = dropdown_area.get_attribute('innerHTML')
                        # Look for dropdown-related content
                        if 'dropdown' in dropdown_html.lower() or 'menu' in dropdown_html.lower():
                            print("Dropdown/menu content detected in page")
                        else:
                            print("No dropdown/menu content detected")
                    except:
                        pass
                        
                except Exception as debug_error:
                    print(f"Error during dropdown debugging: {debug_error}")
                
                if attempt == max_retries - 1:  # Last attempt
                    raise Exception(f"Could not find dropdown option with text '{value}' using any pattern after {max_retries} attempts")
                else:
                    print(f"Option not found in attempt {attempt + 1}, retrying...")
                    # Try to close dropdown and retry
                    try:
                        driver.send_keys(Keys.ESCAPE)
                    except:
                        pass
                    time.sleep(1)
                    continue
                    
        except Exception as attempt_error:
            print(f"Dropdown attempt {attempt + 1} failed: {type(attempt_error).__name__} - {attempt_error}")
            traceback.print_exc() # Print full traceback
            if attempt == max_retries - 1:  # Last attempt
                raise attempt_error
            else:
                # Try to close any open dropdowns and retry
                try:
                    driver.send_keys(Keys.ESCAPE)
                except:
                    pass
                time.sleep(1)
                continue
    
    return False

# --- Selenium Execution ---
def execute_selenium_action(driver, instruction) -> tuple[bool, str | None]:
    if not instruction:
        return False, "Instruction object was None."

    action = instruction.get('action')
    selector_type_str = instruction.get('selector_type')
    selector = instruction.get('selector')
    value = instruction.get('value')
    option_selector = instruction.get('option_selector')
    element = None
    switched_to_iframe = False
    final_error_message = None

    print(f"--- Executing Action: {action} ---")
    print(f"Selector Type: {selector_type_str}, Selector: {selector}")
    if value is not None:
        print(f"Value: {value}")

    if selector_type_str == 'css':
        by_strategy = By.CSS_SELECTOR
    elif selector_type_str == 'xpath':
        by_strategy = By.XPATH
    else:
        final_error_message = f"Unsupported selector type: {selector_type_str}"
        print(f"--- Error: {final_error_message} ---")
        return False, final_error_message

    # Use longer timeout for dropdown operations
    timeout = DROPDOWN_WAIT_TIMEOUT if action in ['select_dropdown', 'click_dropdown_option'] else WAIT_TIMEOUT
    wait = WebDriverWait(driver, timeout)

    try:
        print("Attempting to find element in default content...")
        try:
            if action in ['click', 'hover']:
                element = wait.until(EC.element_to_be_clickable((by_strategy, selector)))
            elif action == 'select_dropdown':
                element = wait.until(EC.presence_of_element_located((by_strategy, selector)))
                # Verify it's a select element
                if element.tag_name.lower() != 'select':
                    raise Exception(f"Element is not a <select> tag, found: {element.tag_name}")
            else:
                element = wait.until(EC.presence_of_element_located((by_strategy, selector)))
            print("Element found in default content.")
        except TimeoutException:
            print("Element not found in default content.")
            final_error_message = f"Timeout: Element with selector '{selector}' (type: {selector_type_str}) not found or not interactable in default content."
            element = None

        if element is None:
            print("Attempting to find element within an iframe...")
            try:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                if not iframes:
                    print("No iframes found on the page.")
                else:
                    print(f"Found {len(iframes)} iframe(s). Checking them for the element...")
                    original_error_from_default = final_error_message
                    found_in_iframe = False
                    for iframe_to_check in iframes:
                        try:
                            iframe_id_name = iframe_to_check.get_attribute('id') or iframe_to_check.get_attribute('name') or iframe_to_check.get_attribute('title') or "N/A"
                            print(f"Switching to iframe: {iframe_id_name}")
                            driver.switch_to.frame(iframe_to_check)
                            switched_to_iframe = True

                            if action in ['click', 'hover']:
                                element = wait.until(EC.element_to_be_clickable((by_strategy, selector)))
                            elif action == 'select_dropdown':
                                element = wait.until(EC.presence_of_element_located((by_strategy, selector)))
                                # Verify it's a select element
                                if element.tag_name.lower() != 'select':
                                    raise Exception(f"Element is not a <select> tag, found: {element.tag_name}")
                            else:
                                element = wait.until(EC.presence_of_element_located((by_strategy, selector)))
                            print(f"Element found within iframe: {iframe_id_name}")
                            found_in_iframe = True
                            final_error_message = None
                            break
                        except TimeoutException:
                            print(f"Element not found in iframe: {iframe_id_name}")
                            driver.switch_to.default_content()
                            switched_to_iframe = False
                        except Exception as e_iframe_switch:
                            print(f"Error while trying to switch or find in iframe {iframe_id_name}: {e_iframe_switch}")
                            if switched_to_iframe:
                                driver.switch_to.default_content()
                            switched_to_iframe = False
                            continue

                    if not found_in_iframe:
                        print("Element not found in any of the iframes.")
                        final_error_message = f"Element with selector '{selector}' (type: {selector_type_str}) not found in default content (error: {original_error_from_default}) nor within any of the {len(iframes)} iframes checked."
                        if switched_to_iframe:
                            driver.switch_to.default_content()
                            switched_to_iframe = False
            except Exception as iframe_err:
                detail = str(iframe_err).split('\n')[0]
                final_error_message = f"Error during general iframe handling phase: {detail}"
                print(f"--- Error during iframe handling: {final_error_message} ---")
                if switched_to_iframe:
                     driver.switch_to.default_content()
                     switched_to_iframe = False

        if element is None:
             print(f"--- Action Failed: Element not located. Final error: {final_error_message} ---")
             if switched_to_iframe:
                 driver.switch_to.default_content()
             return False, final_error_message if final_error_message else f"Element with selector '{selector}' (type: {selector_type_str}) could not be located for action '{action}' after all checks."

        if action == 'click':
            element.click()
            print("Clicked element.")
        elif action == 'type':
            try:
                driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", element)
                time.sleep(0.2)
                element.clear()
                element.send_keys(value)
                print(f"Typed '{value}' into element.")
            except ElementNotInteractableException:
                print("--- Element not interactable for 'type' action. Trying to click it first. ---")
                try:
                    # This often happens with custom inputs that need to be clicked to activate
                    element.click()
                    time.sleep(0.5)
                    element.send_keys(value)
                    print(f"Clicked and then typed '{value}' into element.")
                except Exception as e2:
                    # Re-raise original exception if fallback fails
                    final_error_message = f"Element not interactable for 'type', and fallback click also failed: {e2}"
                    print(f"--- Error: {final_error_message} ---")
                    if switched_to_iframe:
                        driver.switch_to.default_content()
                    return False, final_error_message
        elif action == 'scroll_to_element':
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            print("Scrolled to element.")
        elif action == 'hover':
            actions = ActionChains(driver)
            actions.move_to_element(element).perform()
            print("Hovered over element.")
            time.sleep(1)  # Wait for hover effects
        elif action == 'select_dropdown':
            try:
                select = Select(element)
                # Try to select by visible text first
                try:
                    select.select_by_visible_text(value)
                    print(f"Selected option by visible text: '{value}'")
                except NoSuchElementException:
                    # If that fails, try by value
                    try:
                        select.select_by_value(value)
                        print(f"Selected option by value: '{value}'")
                    except NoSuchElementException:
                        # If that fails, try partial text match
                        options = select.options
                        found = False
                        for option in options:
                            if value.lower() in option.text.lower():
                                select.select_by_visible_text(option.text)
                                print(f"Selected option by partial text match: '{option.text}'")
                                found = True
                                break
                        if not found:
                            available_options = [opt.text for opt in options]
                            raise Exception(f"Could not find option '{value}' in dropdown. Available options: {available_options}")
            except Exception as select_error:
                final_error_message = f"Failed to select dropdown option '{value}': {select_error}"
                print(f"--- Error: {final_error_message} ---")
                if switched_to_iframe:
                    driver.switch_to.default_content()
                return False, final_error_message
        elif action == 'click_dropdown_option':
            try:
                success = handle_dropdown_with_retry(driver, element, value, option_selector)
                if not success:
                    # Try alternative approaches as fallback
                    print("Standard dropdown handling failed, trying alternative approaches...")
                    
                    # Approach 1: Try using ActionChains to click and then find option
                    try:
                        print("Trying ActionChains approach...")
                        actions = ActionChains(driver)
                        actions.click(element).perform()
                        time.sleep(2)
                        
                        # Try to find option with more generic patterns
                        fallback_patterns = [
                            f"//*[contains(text(), '{value}')]",
                            f"//*[text()='{value}']",
                            f"//*[normalize-space()='{value}']"
                        ]
                        
                        for pattern in fallback_patterns:
                            try:
                                option_elem = WebDriverWait(driver, 3).until(
                                    EC.element_to_be_clickable((By.XPATH, pattern))
                                )
                                option_elem.click()
                                print(f"Successfully clicked option using fallback pattern: {pattern}")
                                success = True
                                break
                            except:
                                continue
                                
                    except Exception as fallback_error:
                        print(f"ActionChains fallback failed: {fallback_error}")
                    
                    # Approach 2: Try keyboard navigation
                    if not success:
                        try:
                            print("Trying keyboard navigation approach...")
                            element.click()
                            time.sleep(1)
                            
                            # Send arrow keys to navigate and Enter to select
                            from selenium.webdriver.common.keys import Keys
                            
                            # Try a few arrow downs and check text
                            for i in range(10):  # Try up to 10 options
                                element.send_keys(Keys.ARROW_DOWN)
                                time.sleep(0.3)
                                
                                # Check if we can find the current selected option
                                try:
                                    # Look for focused or selected elements
                                    focused_elements = driver.find_elements(By.XPATH, "//*[contains(@class, 'focused') or contains(@class, 'selected') or contains(@class, 'active')]")
                                    for focused in focused_elements:
                                        if value.lower() in focused.text.lower():
                                            element.send_keys(Keys.ENTER)
                                            print(f"Successfully selected option using keyboard navigation")
                                            success = True
                                            break
                                except:
                                    continue
                                    
                                if success:
                                    break
                                    
                        except Exception as keyboard_error:
                            print(f"Keyboard navigation fallback failed: {keyboard_error}")
                    
                    if not success:
                        raise Exception(f"Failed to select dropdown option '{value}' after all retry attempts and fallback methods")
                        
            except Exception as dropdown_error:
                final_error_message = f"Failed to select dropdown option '{value}': {dropdown_error}"
                print(f"--- Error: {final_error_message} ---")
                if switched_to_iframe:
                    driver.switch_to.default_content()
                return False, final_error_message
        else:
            final_error_message = f"Unsupported action '{action}' at execution stage."
            print(f"--- Error: {final_error_message} ---")
            if switched_to_iframe:
                driver.switch_to.default_content()
            return False, final_error_message

        print("--- Action Execution Successful ---")
        time.sleep(SHORT_DELAY)
        if switched_to_iframe:
            print("Switching back to default content from iframe after successful action.")
            driver.switch_to.default_content()
        return True, None

    except (NoSuchElementException, TimeoutException) as e:
        detail = str(e).split('\n')[0]
        final_error_message = f"Outer Catch: Action '{action}' failed for selector '{selector}' (type: {selector_type_str}). Error: {detail}"
        print(f"--- Action Failed (Outer Catch): {final_error_message} ---")
        if switched_to_iframe:
            driver.switch_to.default_content()
        return False, final_error_message
    except Exception as e:
        detail = str(e).split('\n')[0]
        final_error_message = f"Runtime Error during action '{action}' with selector '{selector}': {detail}"
        print(f"--- Action Execution Failed (Runtime Error) ---")
        print(f"Instruction: {instruction}")
        print(traceback.format_exc())
        if switched_to_iframe:
            driver.switch_to.default_content()
        return False, final_error_message

# --- Main Execution Logic ---
def main():
    global rag_system
    
    # Initialize RAG system
    print("Initializing RAG system...")
    try:
        rag_system = MilvusRAGSystem()
        print("RAG system initialized successfully!")
    except Exception as e:
        print(f"Warning: Failed to initialize RAG system: {e}")
        print("Continuing without RAG support...")
        rag_system = None
    
    driver = setup_driver()
    initial_url = "https://bitnous.sentry.io" # Example
    
    # Get user goal - this could be from command line args, input, or hardcoded for testing
    user_goal = input("\nPlease enter your goal (what you want to accomplish): ").strip()
    if not user_goal:
        # Fallback to example goal for testing
        user_goal = "I want to log in, then find and click '30 days' in a time range selector, and finally wait for 5 seconds."
        print(f"Using default goal: {user_goal}")

    print(f"Navigating to: {initial_url}")
    driver.get(initial_url)
    time.sleep(3) # Initial wait for page load, adjust as needed

    # Check if credentials are needed and prompt user if necessary
    print("\n--- Checking if credentials are required ---")
    html_content = driver.page_source
    credential_check = needs_credentials(user_goal, html_content)
    
    if credential_check['missing_credentials']:
        print(f"Missing credentials detected: {', '.join(credential_check['missing_credentials'])}")
        print("You will be prompted to enter the required credentials.")
        
        credentials = prompt_for_credentials(credential_check['missing_credentials'])
        
        if credentials:
            print("Credentials collected successfully.")
            user_goal = update_goal_with_credentials(user_goal, credentials)
            print(f"Updated goal: {user_goal}")
        else:
            print("Failed to collect required credentials. Exiting.")
            driver.quit()
            return
    else:
        print("No missing credentials detected.")

    completed_step_descriptions_for_context = []
    last_step_generation_or_execution_error = None
    MAX_MAIN_ITERATIONS = 10 # Safety break for the main loop generating sequences of steps
    MAX_ACTION_RETRIES = 2   # Max retries for a single Selenium action (e.g., if LLM gives bad selector first time)
    MAX_CREDENTIAL_RETRIES = 3  # Maximum number of times to re-prompt for credentials
    credential_retry_count = 0

    for main_iteration in range(MAX_MAIN_ITERATIONS):
        print(f"\n--- Main Iteration {main_iteration + 1}/{MAX_MAIN_ITERATIONS} ---")
        print(f"--- Requesting new sequence of steps from LLM for goal: \"{user_goal[:100]}...\" ---")
        if last_step_generation_or_execution_error:
            print(f"--- Context from previous failure: {last_step_generation_or_execution_error} ---")

        current_step_sequence_descriptions = get_llm_web_steps(
            driver,
            user_goal,
            completed_step_descriptions_for_context,
            last_step_generation_or_execution_error
        )
        last_step_generation_or_execution_error = None # Reset

        if current_step_sequence_descriptions is None:
            print("Critical error: Failed to get step sequence from LLM. Stopping.")
            break
        if not current_step_sequence_descriptions: # Empty list means LLM thinks goal is done or stuck
            print("LLM indicates no more steps or goal possibly achieved. Ending process.")
            break

        sequence_fully_successful = True
        for step_index, step_data in enumerate(current_step_sequence_descriptions):
            step_description = step_data["description"]
            print(f"\n=== Processing Generated Step {step_index + 1}/{len(current_step_sequence_descriptions)}: {step_description[:70]}... ===")

            # Handle HUMAN_DECISION steps
            if step_description.upper().startswith("HUMAN_DECISION:"):
                decision_info = parse_human_decision_step(step_description)
                if decision_info:
                    user_decision = prompt_user_decision(
                        decision_info["context"],
                        decision_info["question"],
                        decision_info["options"],
                        decision_info["decision_type"]
                    )
                    
                    if user_decision:
                        success_message = f"Human decision made: {decision_info['question']} -> {user_decision}"
                        completed_step_descriptions_for_context.append(success_message)
                        
                        # Update the user goal to include the decision context
                        decision_context = f"Based on the user's decision for '{decision_info['question']}', the user chose: {user_decision}. "
                        if decision_context not in user_goal:
                            # Add decision context to help future LLM calls
                            completed_step_descriptions_for_context.append(f"Decision context: {decision_context}")
                        
                        print(f"=== Human Decision Step COMPLETED: User chose '{user_decision}' ===")
                        continue  # Move to next step
                    else:
                        print("=== Human Decision Step FAILED: User didn't provide a decision ===")
                        last_step_generation_or_execution_error = f"Human decision required but user didn't provide input for: {decision_info['question']}"
                        sequence_fully_successful = False
                        break
                else:
                    print(f"=== Error: Could not parse HUMAN_DECISION step: {step_description} ===")
                    last_step_generation_or_execution_error = f"Malformed HUMAN_DECISION step: {step_description}"
                    sequence_fully_successful = False
                    break

            # Handle special "wait" command directly
            elif "wait for" in step_description.lower() and "seconds" in step_description.lower():
                try:
                    wait_time_match = re.search(r'(\d+)', step_description)
                    if wait_time_match:
                        wait_time = int(wait_time_match.group(1))
                        print(f"--- Executing special command: Wait for {wait_time} seconds. ---")
                        time.sleep(wait_time)
                        success_message = f"Successfully executed: {step_description}"
                        completed_step_descriptions_for_context.append(success_message)
                        print(f"=== Step '{step_description[:60]}' (Special Wait) SUCCEEDED ===")
                        continue # Move to the next step in the sequence
                    else:
                        print(f"--- Failed to parse wait time from '{step_description}'. Skipping this wait command. ---")
                        last_step_generation_or_execution_error = f"Could not parse wait time for step: '{step_description}'."
                        # Don't mark sequence as failed, just skip this malformed wait
                        continue
                except Exception as e:
                    print(f"--- Error executing wait command '{step_description}': {e} ---")
                    last_step_generation_or_execution_error = f"Error in wait command '{step_description}': {e}"
                    sequence_fully_successful = False # Mark sequence as failed due to error in wait
                    break # Break from this sequence, re-prompt get_llm_web_steps

            # For regular steps, get Selenium instruction and execute
            else:
                action_successful = False
                current_action_error_context = None # Error context for retrying get_llm_instruction

                for attempt in range(MAX_ACTION_RETRIES):
                    print(f"--- Attempt {attempt + 1}/{MAX_ACTION_RETRIES} for action: '{step_description[:60]}' ---")
                    selenium_action_instruction = get_llm_instruction(driver, step_description, current_action_error_context)
                    current_action_error_context = None # Reset for next potential retry within this action

                    if selenium_action_instruction:
                        success, execution_error_msg = execute_selenium_action(driver, selenium_action_instruction)
                        if success:
                            print(f"=== Step '{step_description[:60]}' SUCCEEDED ===")
                            completed_step_descriptions_for_context.append(f"Successfully executed: {step_description}")
                            action_successful = True
                            break # Selenium action successful, break from MAX_ACTION_RETRIES loop
                        else:
                            print(f"--- Selenium execution FAILED for '{step_description[:60]}': {execution_error_msg} ---")
                            
                            # Capture detailed debug info for dropdown failures
                            if 'dropdown' in step_description.lower() or 'select' in step_description.lower() or 'option' in step_description.lower():
                                try:
                                    failed_selector = selenium_action_instruction.get('selector', '') if selenium_action_instruction else ''
                                    debug_info = capture_dropdown_debug_info(driver, failed_selector)
                                    print(f"--- Dropdown Debug Info ---\n{debug_info}\n--- End Debug Info ---")
                                    current_action_error_context = f"{execution_error_msg}\n\nDETAILED DEBUG INFO:\n{debug_info}"
                                except Exception as debug_error:
                                    print(f"Error capturing debug info: {debug_error}")
                                    current_action_error_context = execution_error_msg
                            else:
                                current_action_error_context = execution_error_msg # Use this error for the next get_llm_instruction call
                            
                            # Check if this is an authentication error
                            current_html = driver.page_source
                            if is_authentication_error(execution_error_msg, current_html) and credential_retry_count < MAX_CREDENTIAL_RETRIES:
                                print(f"\n--- AUTHENTICATION ERROR DETECTED ---")
                                print(f"Error: {execution_error_msg}")
                                print(f"Credential retry attempt {credential_retry_count + 1}/{MAX_CREDENTIAL_RETRIES}")
                                
                                # Re-prompt for credentials
                                new_credentials = re_prompt_credentials(f"Authentication failed: {execution_error_msg}")
                                
                                if new_credentials:
                                    # Update the goal with new credentials
                                    user_goal = update_goal_with_credentials(user_goal, new_credentials)
                                    print(f"Updated goal with new credentials: {user_goal}")
                                    credential_retry_count += 1
                                    
                                    # Reset the context to restart from login
                                    completed_step_descriptions_for_context = []
                                    last_step_generation_or_execution_error = "Restarting with new credentials due to authentication failure."
                                    sequence_fully_successful = False
                                    break  # Break from action retries and step processing
                                else:
                                    print("Failed to get new credentials. Continuing with current approach.")
                                    if attempt == MAX_ACTION_RETRIES - 1:
                                        last_step_generation_or_execution_error = f"Action '{step_description}' failed after {MAX_ACTION_RETRIES} attempts. Last error: {execution_error_msg}."
                            else:
                                if attempt == MAX_ACTION_RETRIES - 1: # Last retry for this action failed
                                    last_step_generation_or_execution_error = f"Action '{step_description}' failed after {MAX_ACTION_RETRIES} attempts. Last error: {execution_error_msg}."
                
                if not action_successful:
                    sequence_fully_successful = False
                    # Enhance the error context with detailed information about what was found
                    try:
                        current_html = driver.page_source
                        # Get visible elements that might be dropdown options
                        visible_elements = driver.find_elements(By.XPATH, "//*[contains(@class, 'dropdown') or contains(@class, 'menu') or contains(@class, 'option') or contains(@data-test-id, '')]")
                        visible_info = []
                        for elem in visible_elements[:20]:  # Limit to first 20 elements
                            if elem.is_displayed():
                                elem_info = f"Tag: {elem.tag_name}, Text: '{elem.text[:50]}', Class: '{elem.get_attribute('class')}', ID: '{elem.get_attribute('id')}', data-test-id: '{elem.get_attribute('data-test-id')}'"
                                visible_info.append(elem_info)
                        
                        enhanced_error = f"{last_step_generation_or_execution_error}\n\nADDITIONAL CONTEXT:\n"
                        enhanced_error += f"- Current page URL: {driver.current_url}\n"
                        enhanced_error += f"- Page title: {driver.title}\n"
                        if visible_info:
                            enhanced_error += f"- Visible dropdown/menu/option elements found:\n" + "\n".join([f"  {info}" for info in visible_info[:10]])
                        else:
                            enhanced_error += "- No visible dropdown/menu/option elements found on page"
                        
                        # Check if there are any elements with data-test-id attributes
                        test_id_elements = driver.find_elements(By.XPATH, "//*[@data-test-id]")
                        if test_id_elements:
                            test_ids = [elem.get_attribute('data-test-id') for elem in test_id_elements[:15] if elem.get_attribute('data-test-id')]
                            enhanced_error += f"\n- Available data-test-id values: {', '.join(test_ids)}"
                        
                        last_step_generation_or_execution_error = enhanced_error
                    except Exception as context_error:
                        print(f"Error gathering enhanced context: {context_error}")
                    
                    break # Break from processing current_step_sequence_descriptions, go to next main loop to regenerate step sequence

        if not sequence_fully_successful:
            print("--- Current sequence of steps encountered an issue. Attempting to get a new sequence from LLM. ---")
            # The loop will continue, and get_llm_web_steps will be called with last_step_generation_or_execution_error
        else:
            print("--- Successfully completed a sequence of LLM-generated steps. Checking if more steps are needed for the goal... ---")
            # If loop finishes and sequence_fully_successful is true, main loop continues, potentially asking for more steps.
            # If get_llm_web_steps returns [], it indicates completion.

    if credential_retry_count >= MAX_CREDENTIAL_RETRIES:
        print(f"\n--- MAXIMUM CREDENTIAL RETRIES REACHED ({MAX_CREDENTIAL_RETRIES}) ---")
        print("Unable to authenticate after multiple attempts. Please verify your credentials.")

    print("\nScript finished or max iterations reached. Browser will remain open for inspection.")
    # driver.quit() # Commented out to allow inspection

if __name__ == "__main__":
    main()
