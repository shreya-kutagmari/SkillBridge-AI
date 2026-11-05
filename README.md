# SkillBridge AI – Intelligent Career Guidance and Job Matching Platform

## Project Overview

SkillBridge AI is an AI-powered career guidance platform designed to help students and job seekers identify suitable job opportunities, analyze skill gaps, and build personalized learning roadmaps.

The platform combines AI-driven career assistance, resume analysis, job matching, and skill development recommendations to support users in their career journey.

## Key Features

- **AI Career Assistant:** Provides personalized career guidance and recommendations.
- **Resume Analysis:** Analyzes uploaded resumes and provides a resume quality score, detected sections, and improvement suggestions.
- **Job Matching:** Identifies relevant job opportunities based on users' skills.
- **Skill Gap Analysis:** Compares existing skills with job requirements and highlights missing skills.
- **Personalized Learning Roadmaps:** Recommends learning paths to improve employability.
- **Application Tracking:** Helps users track their job applications.
- **Bilingual Career Guidance:** Supports English and Kannada career assistance.

## Technology Stack

- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, JavaScript
- **Database:** SQLite
- **AI Integration:** IBM watsonx.ai
- **AI Agent Platform:** IBM watsonx Orchestrate
- **Document Processing:** PyPDF, python-docx
- **Deployment:** Render
- **Version Control:** Git and GitHub

## Project Structure

```text
SkillBridge_AI/
├── agents/
├── static/
│   ├── css/
│   └── js/
├── templates/
├── tests/
├── uploads/
├── utils/
├── evidence/
├── app.py
├── requirements.txt
├── .env.example
└── README.md
```

## IBM watsonx Orchestrate Integration

A SkillBridge Career Assistant agent was created using IBM watsonx Orchestrate.

- Agent name: SkillBridge Career Assistant
- Version: 1.0.0
- Deployment status: Deployed to Live
- Purpose: Career guidance, job matching, skill-gap analysis, and personalized learning recommendations.

## Installation and Setup

1. Clone the repository:

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd SkillBridge_AI
```

2. Create a virtual environment:

```bash
python -m venv venv
```

3. Activate it on Windows:

```powershell
.\venv\Scripts\Activate.ps1
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Configure environment variables using `.env.example`. Add your own credentials locally. Never commit API keys or secrets.

6. Run the application:

```bash
python app.py
```

7. Open:

```text
http://127.0.0.1:5000
```

## Evidence and Screenshots

The `evidence/` folder contains screenshots documenting:

1. IBM Bob usage
2. SkillBridge Career Assistant profile
3. Agent version 1.0.0
4. Live agent deployment
5. Successful agent response
6. SkillBridge application dashboard
7. Resume analysis
8. Job matching and skill-gap results

## Project Objective

To make career guidance more accessible by helping students understand their current skills, discover relevant opportunities, and identify practical steps toward employment.

## Disclaimer

Job matches and resume scores are guidance tools and should not be interpreted as guaranteed hiring outcomes or official ATS evaluations.