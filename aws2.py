import boto3
import json
import difflib
import spacy
import os
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

def get_pos(word):
    doc = nlp(word)
    return doc[0].pos_ if doc else "UNKNOWN"

def show_grammar_changes(original, result):
    print("\n🔍 Grammar Changes Made:\n")
    original_tokens = original.split()
    result_tokens = result.split()
    diff = list(difflib.ndiff(original_tokens, result_tokens))

    original_index = 0  # Track position in the original sentence

    i = 0
    while i < len(diff):
        line = diff[i]

        if line.startswith("- "):  # Word removed (from original)
            old_word = line[2:]

            # Check if this is a replacement
            if i + 1 < len(diff) and diff[i + 1].startswith("+ "):
                new_words = []
                j = i + 1
                while j < len(diff) and diff[j].startswith("+ "):
                    new_words.append(diff[j][2:])
                    j += 1

                replacement = " ".join(new_words)
                pos = get_pos(replacement.split()[0])
                print(f"🔁 Replaced | Original Index: {original_index} | POS: {pos} | Old: '{old_word}' → New: '{replacement}'")

                i = j
                original_index += 1  # Because 1 word was removed
            else:
                pos = get_pos(old_word)
                print(f"❌ Removed | Original Index: {original_index} | POS: {pos} | Word: '{old_word}'")
                i += 1
                original_index += 1

        elif line.startswith("+ "):  # Word added in result only (no old word removed)
            # We still show where it was added in the original
            new_word = line[2:]
            pos = get_pos(new_word)
            print(f"➕ Added | Inserted At Original Index: {original_index} | POS: {pos} | Word: '{new_word}'")
            i += 1
            # Do NOT increment original_index

        else:  # No change
            i += 1
            original_index += 1


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

# ✅ This makes sure your code doesn’t run twice
if __name__ == "__main__":
        text = input("Enter your text: ")
        generate(text)
