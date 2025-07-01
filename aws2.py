import boto3
import json
import difflib
import spacy
import os
from dotenv import load_dotenv
from botocore.exceptions import ClientError
import string

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

# ANSI Colors for terminal highlighting
RED = '\033[91m'     # Removed
GREEN = '\033[92m'   # Added
BLUE = '\033[94m'    # Replaced
RESET = '\033[0m'
# ANSI Styles
UNDERLINE = '\033[4m'

def get_pos(word):
    doc = nlp(word)
    return doc[0].pos_ if doc else "UNKNOWN"

def is_just_punctuation_change(old_word, new_word):
    return old_word.strip(string.punctuation) == new_word.strip(string.punctuation)

def show_grammar_changes(original, result):
    print("\n🔍 Grammar Changes Made:\n")
    original_tokens = original.split()
    result_tokens = result.split()
    diff = list(difflib.ndiff(original_tokens, result_tokens))
    changes = {
    "replaced": 0,
    "removed": 0,
    "added": 0,
    "total": len(original.split())
    }
    position = 0  # Track position in the original sentence

    i = 0
    while i < len(diff):
        line = diff[i]
        if line.startswith("- "):
            old_word = line[2:]
            j = i + 1
            while j < len(diff) and diff[j].startswith("? "):
                j += 1
            if j < len(diff) and diff[j].startswith("+ "):
                new_word = diff[j][2:]
                if is_just_punctuation_change(old_word, new_word):
                    i = j + 1
                    position += 1
                    continue
                pos = get_pos(new_word)
                print(f"🔁 Replaced | Position: {position} | POS: {pos} | Old: '{old_word}' → New: '{new_word}'| {highlight_replaced(old_word, new_word)}")
                i=j+1
                position+=1
                changes["replaced"] += 1
            else:
                if all(c in string.punctuation for c in diff[i][2:]):
                    i+=1
                    position+=1
                    continue    
                pos = get_pos(old_word)
                print(f"❌ Removed | Position: {position} | POS: {pos} | Word: '{old_word}'| {highlight_removed(old_word)}")
                i += 1
                position+=1
                changes["removed"] += 1
        elif line.startswith("+ "):
            new_word = line[2:]
            if all(c in string.punctuation for c in new_word):
                    i+=1
                    position+=1
                    continue 
            pos = get_pos(new_word)
            print(f"➕ Added | Position: {position} | POS: {pos} | Word: '{new_word}'| {highlight_added(new_word)}")
            i += 1
            changes["added"] += 1
        else:
            i += 1
        if not (line.startswith("?") or line.startswith("+") or line.startswith("-")):
            position+=1 
    score, breakdown = compute_detailed_score(changes)
    print(f"\n📊 Grammar Score Breakdown:")
    for k, v in breakdown.items():
        print(f"   {k:<10}: {v}/25")
    print(f"\n✅ Final Grammar Score: {score}/100")      

def highlight_removed(word):
    return f"{RED}{word}{RESET}"

def highlight_added(word):
    return f"{GREEN}{word}{RESET}"

def highlight_replaced(old, new):
    return f"{BLUE}{old} → {new}{RESET}"

def format_replaced(old, new):
    return f"{UNDERLINE}{old}{RESET} (removed) {new} (added)"

def format_removed(word):
    return f"{UNDERLINE}{word}{RESET} (removed)"

def format_added(word):
    return f"{UNDERLINE}{word}{RESET} (added)"

def get_highlighted_paragraph(original, result):
    original_tokens = original.split()
    result_tokens = result.split()
    diff = list(difflib.ndiff(original_tokens, result_tokens))
    highlighted = []
    i = 0
    while i < len(diff):
        line = diff[i]
        
        if line.startswith("- "):
            old_word = line[2:]
            j = i + 1
            while j < len(diff) and diff[j].startswith("? "):
                j += 1
            if j < len(diff) and diff[j].startswith("+ "):
                new_word = diff[j][2:]
                if is_just_punctuation_change(old_word, new_word):
                    highlighted.append(new_word)
                    i = j + 1
                    continue
                highlighted.append(format_replaced(old_word, new_word))
                i = j + 1
            else:
                if all(c in string.punctuation for c in old_word):
                    i += 1
                    continue
                highlighted.append(format_removed(old_word))
                i += 1
        elif line.startswith("+ "):
            new_word = line[2:]
            if all(c in string.punctuation for c in new_word):
                highlighted.append(new_word)
                i += 1
                continue
            highlighted.append(format_added(new_word))
            i += 1
        elif not line.startswith("? "):
            # unchanged word
            highlighted.append(line[2:])
            i += 1
        else:
            i += 1

    return " ".join(highlighted)

        
def compute_detailed_score(changes):
    total_tokens = changes['total']
    total_edits = changes['replaced'] + changes['removed'] + changes['added']

    if total_tokens == 0:
        return 100, {"Clarity": 25, "Fluency": 25, "Brevity": 25, "Accuracy": 25}

    # 🧮 Subscores
    clarity_deduction = min(25, changes['replaced'] * 1.5)  # replacements
    fluency_deduction = min(25, changes['added'] * 1)       # additions
    brevity_deduction = min(25, changes['removed'] * 1.2)   # removals

    # overall penalty for edit density
    edit_ratio = total_edits / total_tokens
    accuracy_score = max(0, 25 - (edit_ratio * 25))

    # Individual scores
    clarity_score = max(0, 25 - clarity_deduction)
    fluency_score = max(0, 25 - fluency_deduction)
    brevity_score = max(0, 25 - brevity_deduction)

    total_score = int(clarity_score + fluency_score + brevity_score + accuracy_score)
    breakdown = {
        "Clarity": round(clarity_score, 2),
        "Fluency": round(fluency_score, 2),
        "Brevity": round(brevity_score, 2),
        "Accuracy": round(accuracy_score, 2)
    }

    return total_score, breakdown    

def generate(original):
    load_dotenv()
    region_name = os.getenv('AWS_REGION') or "us-east-1"
    bedrock = boto3.client("bedrock-runtime", region_name=region_name)

    sys_prompt = f"""You are a grammar correction tool. Your task is to ONLY fix grammar, sentence structure, or punctuation. 
You must NOT change the meaning, rephrase sentences, or add new content. Get rid of the filler words. Give the result only once dont repeat the same output more than once.
For example if we have an input such as i went to the market dont repeat i went to the market twice in the output.
Keep the structure, tone, and context exactly the same — only fix what's grammatically wrong. Do not include any text before or after the output.
Correct this text:
{original}
Return only the corrected version."""
    question=f'''correct this transcription data- {original} '''    
    header = "<|start_header_id|>system<|end_header_id|>\nYour system prompt here<|eot_id|>\n"
    chat_history_formatted=sys_prompt
    msg = f"<|start_header_id|>user<|end_header_id|>\n{question}<|eot_id|>\n<|start_header_id|>assistant<|end_header_id|>\n"
    final_prompt = header + chat_history_formatted + msg

    json_payload = json.dumps({
        "prompt": final_prompt,
        "temperature": 0
    })

    try:
        response = bedrock.invoke_model(
            modelId="meta.llama3-3-70b-instruct-v1:0",
            body=json_payload,
            contentType="application/json",
            accept="application/json"
        )
        raw = json.loads(response['body'].read())
        result = raw['generation'].strip()

        # 🧹 Optional: If model adds "Corrected sentence:" at the start
        if result.lower().startswith("corrected"):
            result = result.split(":", 1)[-1].strip()

        print(f"\n✅ Corrected Output:\n{result}")
        show_grammar_changes(original, result)

    except ClientError as e:
        print(f"ClientError: {e}")
    except json.JSONDecodeError:
        print("❌ Failed to decode LLaMA response.")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
    
    highlighted_paragraph = get_highlighted_paragraph(original, result)
    print(f"\n🖍️ Highlighted Paragraph:\n{highlighted_paragraph}")


if __name__ == "__main__":
        i=0
        while(i<10):
            text = input("Enter your text: ")
            generate(text)
            i+=1
