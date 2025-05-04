from ollama import chat, ChatResponse
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

# --- Configuration ---
LLM_MODEL = 'deepseek-r1:7b-qwen-distill-q8_0'
WAIT_TIMEOUT = 10 # Seconds to wait for elements
SHORT_DELAY = 2 # Seconds delay after action

# --- Selenium Setup ---
def setup_driver():
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    # options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

# --- LLM Interaction ---
def get_llm_instruction(driver, step_description):
    print(f"\n--- Requesting Instruction for Step: {step_description[:60]}... ---")
    html_content = driver.page_source
    # Example structure to guide the LLM
    json_example = '''
    {
      "action": "type|click|scroll_to_element",
      "selector_type": "css|xpath",
      "selector": "<Your CSS or XPath selector here>",
      "value": "<Text to type, only if action is 'type'>" // Optional
    }
    '''
    prompt = f"""
Given the current HTML content of the webpage, provide a JSON object specifying the Selenium action needed to perform the following task.

Task:
{step_description}

HTML Content Snippet (first 5000 chars):
---
{html_content[:5000]}...
---

Respond ONLY with a single JSON object in the following format (do not include ```json markers or any other text):
{json_example}

Choose the simplest and most reliable selector (CSS preferably, XPath if necessary).
Ensure the 'action' is one of 'click', 'type', or 'scroll_to_element'.
Include the 'value' key ONLY if the action is 'type'.

JSON Instruction:
"""
    instruction = None
    json_string = None
    try:
        response: ChatResponse = chat(model=LLM_MODEL, messages=[
            {
                'role': 'user',
                'content': prompt,
            },
        ], options={"temperature": 0.1}) # Lower temperature for more predictable JSON

        raw_response = response['message']['content'].strip()
        print(f"--- Raw LLM Response ---\n{raw_response}\n------------------------")

        # Attempt to extract JSON object using regex
        match = re.search(r'\{.*?\}', raw_response, re.DOTALL)
        if match:
            json_string = match.group(0)
            print(f"--- Extracted JSON String ---\n{json_string}\n---------------------------")
            # Attempt to parse the extracted JSON string
            instruction = json.loads(json_string)

            # Basic validation
            if not all(k in instruction for k in ['action', 'selector_type', 'selector']):
                print("--- Error: Parsed JSON missing required keys. ---")
                instruction = None # Invalidate instruction
            elif instruction['action'] == 'type' and 'value' not in instruction:
                 # This case is handled later in main loop, so just log here
                 print("--- Info: LLM response for 'type' action missing 'value' (will use predefined). ---")
            elif instruction['selector_type'] not in ['css', 'xpath']:
                 print("--- Error: Parsed JSON has invalid 'selector_type'. ---")
                 instruction = None # Invalidate instruction

        else:
            print("--- Error: Could not find JSON object in LLM response. ---")

        if instruction:
             print(f"--- Parsed Instruction ---\n{json.dumps(instruction, indent=2)}\n--------------------------")

        return instruction # Return instruction or None

    except json.JSONDecodeError as jde:
        print(f"--- Error: Failed to decode extracted JSON string: {jde} ---")
        print(f"Extracted string was: {json_string}")
        return None
    except Exception as e:
        print(f"--- Error during LLM call or JSON processing: {e} ---")
        print(traceback.format_exc())
        return None

# --- Selenium Execution ---
def execute_selenium_action(driver, instruction):
    if not instruction:
        return False

    action = instruction.get('action')
    selector_type_str = instruction.get('selector_type')
    selector = instruction.get('selector')
    value = instruction.get('value') # Will be None if not present

    print(f"--- Executing Action: {action} ---")
    print(f"Selector Type: {selector_type_str}, Selector: {selector}")
    if value is not None:
        print(f"Value: {value}")

    try:
        # Determine By strategy
        if selector_type_str == 'css':
            by_strategy = By.CSS_SELECTOR
        elif selector_type_str == 'xpath':
            by_strategy = By.XPATH
        else:
            print(f"--- Error: Unsupported selector type: {selector_type_str} ---")
            return False

        # Wait for element presence
        wait = WebDriverWait(driver, WAIT_TIMEOUT)
        if action == 'click' or action == 'type' or action == 'scroll_to_element':
             # For click/type wait for clickable/visible, for scroll just presence is enough initially
             if action == 'click':
                 element = wait.until(EC.element_to_be_clickable((by_strategy, selector)))
             else: # type or scroll_to_element
                 element = wait.until(EC.presence_of_element_located((by_strategy, selector)))
        else:
            print(f"--- Error: Unsupported action: {action} ---")
            return False

        # Perform the action
        if action == 'click':
            element.click()
            print("Clicked element.")
        elif action == 'type':
            element.clear() # Clear field before typing
            element.send_keys(value)
            print(f"Typed '{value}' into element.")
        elif action == 'scroll_to_element':
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            print("Scrolled to element.")
            time.sleep(0.5) # Small pause after scroll

        print("--- Action Execution Successful ---")
        time.sleep(SHORT_DELAY) # Add a small delay after successful action
        return True

    except (NoSuchElementException, TimeoutException) as e:
        print(f"--- Action Failed: Element not found or timeout ---")
        print(f"Selector: {by_strategy} = {selector}")
        print(f"Error Details: {e}")
        return False
    except Exception as e:
        print(f"--- Action Execution Failed (Runtime Error) ---")
        print(f"Instruction: {instruction}")
        print(traceback.format_exc())
        print("---------------------------")
        return False

# --- Main Execution Logic ---
def main():
    driver = setup_driver()
    url = "https://sentry.tools.upcastr.co/auth/login/upcastr/?referrer=slack"
    print(f"Navigating to: {url}")
    driver.get(url)
    time.sleep(5) # Wait for initial page load

    # Define sequence of steps with descriptions for the LLM
    steps = [
        {"description": "Find the email input field and prepare to type in it.", "expected_action": "type"},
        {"description": "Type the email 'sharjeel@upcastr.co' into the focused field.", "email_value": "sharjeel@upcastr.co"},
        {"description": "Find the password input field and prepare to type in it.", "expected_action": "type"},
        {"description": "Type the password 'hpg!jbn9jbw.tfd0UVJ' into the focused field.", "password_value": "hpg!jbn9jbw.tfd0UVJ"},
        {"description": "Find and click the login button.", "expected_action": "click"},
        # Assuming login redirects or updates the page significantly
        {"description": "After login, find and click the element acting as a time range selector dropdown (e.g., might contain text like 'Last 24 hours' or '7d').", "expected_action": "click"},
        {"description": "From the opened dropdown/options, find and click the option representing '30 days'.", "expected_action": "click"},
        {"description": "Scroll down the page to make the element representing the 'largest event' visible.", "expected_action": "scroll_to_element"}
        # Note: Interacting with the 'largest event' after scrolling would be another step.
    ]

    # Add login details directly to relevant steps for the LLM
    steps[1]["description"] = f"Type the email '{steps[1]['email_value']}' into the email field found in the previous step."
    steps[3]["description"] = f"Type the password '{steps[3]['password_value']}' into the password field found in the previous step."

    # Pre-populate 'value' for type actions to simplify LLM task slightly
    steps[1]["value"] = steps[1]["email_value"]
    steps[3]["value"] = steps[3]["password_value"]

    for i, step_data in enumerate(steps):
        step_description = step_data["description"]
        print(f"\n=== Processing Step {i+1}/{len(steps)}: {step_description[:60]}... ===")

        instruction = get_llm_instruction(driver, step_description)

        # If LLM didn't provide a value for typing, use the one from our steps data
        if instruction and instruction.get('action') == 'type' and 'value' not in instruction:
            if 'value' in step_data:
                instruction['value'] = step_data['value']
                print(f"--- Added predefined value '{instruction['value']}' to instruction ---")
            else:
                 print(f"--- Warning: Type action requested by LLM, but no value provided or found in step data. --- ")
                 instruction = None # Invalidate instruction if type value is missing

        if instruction:
            if not execute_selenium_action(driver, instruction):
                print(f"Stopping execution due to error in step {i+1}.")
                break # Stop if execution fails
            print(f"=== Step {i+1} Completed ===")
        else:
            print(f"Could not get valid instruction for step {i+1}. Stopping.")
            break

    print("\nScript finished. Browser will remain open for inspection.")
    # driver.quit() # Commented out to allow inspection

if __name__ == "__main__":
    main()