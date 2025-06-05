from selenium import webdriver
from selenium.common import NoSuchElementException, TimeoutException # Import specific exceptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import traceback
import re
import json # Import json module
import requests # Import requests module
from rag_system import MilvusRAGSystem # Import RAG system

# --- Configuration ---
GEMINI_API_KEY = "AIzaSyCGQJM3AcplIqN7jYGIsy-ETMEjPz9ndPo" # Added Gemini API Key
LLM_MODEL = 'gemini-2.0-flash' # Updated to use a Gemini model identifier
WAIT_TIMEOUT = 10 # Seconds to wait for elements
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
    """
    updated_goal = user_goal
    
    # Add credentials to the beginning of the goal
    credential_text = ""
    if 'username' in credentials:
        credential_text += f"My username is {credentials['username']}"
    if 'password' in credentials:
        if credential_text:
            credential_text += f" and password is {credentials['password']}. "
        else:
            credential_text += f"My password is {credentials['password']}. "
    
    if credential_text:
        # Check if goal already starts with credential info
        goal_lower = updated_goal.lower()
        if not any(pattern in goal_lower[:50] for pattern in ['username is', 'password is', 'my username', 'my password']):
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
    MAX_HTML_LEN = 100000 # Approx 100KB
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
Please analyze the goal, HTML, and previous error to generate a revised sequence of steps. If the error indicates an element was not found, try to find a different way or identify if the goal up to that point is unachievable with the current page.
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
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{LLM_MODEL}:generateContent?key={GEMINI_API_KEY}"
        headers = {'Content-Type': 'application/json'}
        data = {
            "contents": [{"parts":[{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }
        response = requests.post(api_url, headers=headers, json=data, timeout=45)
        response.raise_for_status()
        raw_response_json = response.json()

        if raw_response_json.get('candidates') and \
           raw_response_json['candidates'][0].get('content') and \
           raw_response_json['candidates'][0]['content'].get('parts') and \
           raw_response_json['candidates'][0]['content']['parts'][0].get('text'):
            json_string = raw_response_json['candidates'][0]['content']['parts'][0]['text']
            print(f"--- Extracted JSON String for steps ---\n{json_string}\n---------------------------")
            parsed_steps = json.loads(json_string)
            if not isinstance(parsed_steps, list):
                print("--- Error: Parsed JSON for steps is not a list. ---")
                return None
            for step in parsed_steps:
                if not isinstance(step, dict) or "description" not in step:
                    print(f"--- Error: Invalid step format in list: {{step}}. Missing 'description'. ---")
                    return None
            print(f"--- Parsed Step Descriptions ---\n{json.dumps(parsed_steps, indent=2)}\n--------------------------")
            return parsed_steps
        else:
            print("--- Error: Could not find JSON content for steps in Gemini API response. ---")
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
        print(f"--- Error during Gemini API call or JSON processing in get_llm_web_steps: {e} ---")
        print(traceback.format_exc())
        return None

def get_llm_instruction(driver, step_description, previous_error: str | None = None):
    print(f"\n--- Requesting Instruction for Step: {step_description[:60]}... ---")
    if previous_error:
        print(f"--- Previous attempt failed with error: {previous_error} ---")
    html_content = driver.page_source
    MAX_HTML_LEN = 100000 # Approx 100KB
    if len(html_content) > MAX_HTML_LEN:
        print(f"--- Truncating HTML content from {len(html_content)} to {MAX_HTML_LEN} chars for LLM prompt ---")
        html_content = html_content[:MAX_HTML_LEN] + "\n... (HTML truncated) ..."
    json_example = '''
    {
      "action": "type|click|scroll_to_element",
      "selector_type": "css|xpath",
      "selector": "<Your CSS or XPath selector here>",
      "value": "<Text to type, only if action is 'type'>"
    }
    '''
    prompt = f"""
Given the current HTML content of the webpage, provide a JSON object specifying the Selenium action needed to perform the following task.

Task:
{step_description}

HTML Content Snippet (may be truncated):
---
{html_content}
---

Respond ONLY with a single JSON object in the following format (do not include ```json markers or any other text):
{json_example}

Choose the simplest and most reliable selector (CSS preferably, XPath if necessary).
Ensure the 'action' is one of 'click', 'type', or 'scroll_to_element'.
If the action is 'type', the 'value' key MUST be present and contain the text to type. This text should be extracted from the Task description if provided (e.g., if Task is "Type 'hello' into field", value should be "hello").
"""
    if previous_error:
        prompt += f"""
The previous attempt to execute an action for this step failed with the following error:
---
{previous_error}
---
Please analyze the HTML content again and provide a revised JSON instruction to achieve the original task, taking this error into account.
If you believe the element genuinely does not exist or the task is impossible with the current HTML, you can indicate this, but prioritize finding a working selector if possible.
"""
    prompt += """
JSON Instruction:
"""
    instruction = None
    json_string = None
    try:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{LLM_MODEL}:generateContent?key={GEMINI_API_KEY}"
        headers = {'Content-Type': 'application/json'}
        data = {
            "contents": [{"parts":[{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        response = requests.post(api_url, headers=headers, json=data, timeout=30)
        response.raise_for_status()

        raw_response_json = response.json()
        # print(f"--- Raw Gemini API Response ---\n{json.dumps(raw_response_json, indent=2)}\n------------------------")

        if raw_response_json.get('candidates') and raw_response_json['candidates'][0].get('content') and raw_response_json['candidates'][0]['content'].get('parts'):
            json_string = raw_response_json['candidates'][0]['content']['parts'][0]['text']
            # print(f"--- Extracted JSON String ---\n{json_string}\n---------------------------")
            instruction = json.loads(json_string)

            if not all(k in instruction for k in ['action', 'selector_type', 'selector']):
                print("--- Error: Parsed JSON missing required keys (action, selector_type, selector). ---")
                instruction = None
            elif instruction['action'] == 'type' and 'value' not in instruction:
                 print(f"--- Error: Gemini response for 'type' action from description '{step_description[:50]}' missing 'value'. ---")
                 instruction = None # Invalidate instruction
            elif instruction['selector_type'] not in ['css', 'xpath']:
                 print("--- Error: Parsed JSON has invalid 'selector_type'. ---")
                 instruction = None
        else:
            print("--- Error: Could not find JSON content in Gemini API response. ---")
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
        print(f"--- Error during Gemini API call or JSON processing: {e} ---")
        print(traceback.format_exc())
        return None

# --- Selenium Execution ---
def execute_selenium_action(driver, instruction) -> tuple[bool, str | None]:
    if not instruction:
        return False, "Instruction object was None."

    action = instruction.get('action')
    selector_type_str = instruction.get('selector_type')
    selector = instruction.get('selector')
    value = instruction.get('value')
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

    wait = WebDriverWait(driver, WAIT_TIMEOUT)

    try:
        print("Attempting to find element in default content...")
        try:
            if action == 'click':
                element = wait.until(EC.element_to_be_clickable((by_strategy, selector)))
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

                            if action == 'click':
                                element = wait.until(EC.element_to_be_clickable((by_strategy, selector)))
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
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", element)
            time.sleep(0.2)
            element.clear()
            element.send_keys(value)
            print(f"Typed '{value}' into element.")
        elif action == 'scroll_to_element':
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            print("Scrolled to element.")
            time.sleep(0.5)
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
    initial_url = "https://sentry.tools.upcastr.co/auth/login/upcastr/?referrer=slack" # Example
    
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

    for _ in range(MAX_MAIN_ITERATIONS):
        print(f"\n--- Requesting new sequence of steps from LLM for goal: \"{user_goal[:100]}...\" ---")
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
                            current_action_error_context = execution_error_msg # Use this error for the next get_llm_instruction call
                            if attempt == MAX_ACTION_RETRIES - 1: # Last retry for this action failed
                                last_step_generation_or_execution_error = f"Action '{step_description}' failed after {MAX_ACTION_RETRIES} attempts. Last error: {execution_error_msg}."
                    else: # get_llm_instruction returned None
                        print(f"--- LLM FAILED to provide Selenium instruction for '{step_description[:60]}'. ---")
                        current_action_error_context = "LLM did not return a valid Selenium JSON instruction for the step description."
                        if attempt == MAX_ACTION_RETRIES - 1: # Last retry for getting instruction failed
                            last_step_generation_or_execution_error = f"Failed to get Selenium instruction for '{step_description}' after {MAX_ACTION_RETRIES} tries. LLM did not provide a command."
                
                if not action_successful:
                    sequence_fully_successful = False
                    break # Break from processing current_step_sequence_descriptions, go to next main loop to regenerate step sequence

        if not sequence_fully_successful:
            print("--- Current sequence of steps encountered an issue. Attempting to get a new sequence from LLM. ---")
            # The loop will continue, and get_llm_web_steps will be called with last_step_generation_or_execution_error
        else:
            print("--- Successfully completed a sequence of LLM-generated steps. Checking if more steps are needed for the goal... ---")
            # If loop finishes and sequence_fully_successful is true, main loop continues, potentially asking for more steps.
            # If get_llm_web_steps returns [], it indicates completion.

    print("\nScript finished or max iterations reached. Browser will remain open for inspection.")
    # driver.quit() # Commented out to allow inspection

if __name__ == "__main__":
    main()