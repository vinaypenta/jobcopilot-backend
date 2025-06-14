from fastapi import FastAPI
from pydantic import BaseModel
from thefuzz import process
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import openai
import json

# ---------- CONFIGURATION ----------
SPREADSHEET_ID = '15KbEsO8LU4sqwtIHCAvtUS4vJY37iwol8WJd46FUCRE'
SHEET_NAME = 'Sheet7'
PROFILE_PATH = "profile.txt"

with open(PROFILE_PATH, "r", encoding="utf-8") as f:
    PROFILE_TEXT = f.read().strip()

# Read OpenAI API key from credentials/openai_key.txt (never commit this file)
with open("credentials/openai_key.txt") as kf:
    openai.api_key = kf.read().strip()

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials/service_account.json', scope)
gc = gspread.authorize(creds)
worksheet = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

app = FastAPI()

class NameRequest(BaseModel):
    name: str

# ---------- HELPERS ----------

def fuzzy_lookup_person(name):
    data = worksheet.get_all_records()
    names = [row['Name'] for row in data]
    match, score = process.extractOne(name, names)
    for row in data:
        if row['Name'] == match:
            return row
    return None

def extract_jd_info_with_llm(jd_content):
    prompt = (
        "You are given a Job Description (JD). Extract and return as JSON:\n"
        "1. 'job_title': The job title for this position (from the JD content only)\n"
        "2. 'company_name': The company name (from the JD content only, or write 'Unknown' if not present)\n"
        "3. 'x': The most important skill or experience the JD emphasizes (for example: SDK, Risk, B2B SaaS, AI, etc.)\n\n"
        f"JD Content:\n{jd_content}\n"
        "Return JSON: "
    )
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        extracted = json.loads(response.choices[0].message.content.strip().replace("'", "\""))
        return extracted
    except Exception:
        return {"job_title": "Unknown", "company_name": "Unknown", "x": "the required experience"}

# ---------- ENDPOINTS ----------

@app.post("/generate-message")
async def generate_message(req: NameRequest):
    person_row = fuzzy_lookup_person(req.name)
    if not person_row:
        return {"error": "Person not found in sheet"}
    
    jd_content = person_row['JD content']
    jd_link = person_row['JDlink']

    extracted = extract_jd_info_with_llm(jd_content)

    message = f"""Hi {req.name}

I came across the {extracted['job_title']} opening at {extracted['company_name']} and was hoping you could help me better understand what kind of candidate the team is looking for. And if you are focusing our search on someone who has {extracted['x']} experience

If possible, I’d appreciate any guidance—or if there’s someone else I should reach out to, a quick nudge in the right direction would mean a lot. I’ll make sure to keep this discreet.

JD: {jd_link}

{extracted['x']} is dependent on the JD content and my profile. The expectation from the LLM is that it will read the Job Description check what is that one thing that the JD is emphasizing that the candidate should have experience in and my profile and Find {extracted['x']} that will help the message become more persuasive
If this Job role is for PM of an SDK, Risk, B2B SaaS, AI, Identity, API, Hospitality, or AR/VR Product then - {extracted['x']} should be SDK, Risk, B2B SaaS, AI, Identity, API, Hospitality, or AR/VR experience respectively
"""
    return {"message": message}

@app.post("/generate-coverletter")
async def generate_coverletter(req: NameRequest):
    person_row = fuzzy_lookup_person(req.name)
    if not person_row:
        return {"error": "Person not found in sheet"}
    
    jd_content = person_row['JD content']

    prompt = (
        f"Profile:\n{PROFILE_TEXT}\n\n"
        f"Job Description:\n{jd_content}\n\n"
        "Generate a tailored cover letter (formal, professional tone) for this job based on my profile and the JD above."
    )

    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    cover_letter = response.choices[0].message.content.strip()
    return {"cover_letter": cover_letter}

# Optional: Health check endpoint
@app.get("/")
def read_root():
    return {"status": "ok"}

# Generate Answer end point
class AnswerRequest(BaseModel):
    question: str
    jd_content: str

@app.post("/generate-answer")
async def generate_answer(req: AnswerRequest):
    prompt = (
        f"Profile: {PROFILE_TEXT}\n"
        f"Job Description: {req.jd_content}\n"
        f"Question: {req.question}\n"
        "Generate a concise, tailored answer based on the profile and JD."
    )
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    answer = response.choices[0].message.content.strip()
    return {"answer": answer}
