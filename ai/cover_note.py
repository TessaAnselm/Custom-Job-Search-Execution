"""Cover note generation — writes a personalized, non-templated cover note."""

import os
from openai import AsyncOpenAI


class CoverNoteGenerator:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    async def generate(self, job: dict, profile: dict) -> str:
        """Returns a plain-text cover note draft (3–4 paragraphs)."""
        name = profile.get("name", "Candidate")
        skills = ", ".join(profile.get("skills", []))
        experience_years = profile.get("experience_years", "")
        target_titles = ", ".join(profile.get("target_titles", []))
        industries_preferred = ", ".join(profile.get("industries", {}).get("preferred", []))
        base_resume = profile.get("base_resume", "")

        prompt = f"""You are a professional cover letter writer.

Write a cover note for this job application. It should be:
- 3–4 short paragraphs
- Specific to this company and role — not generic
- Honest and direct (no clichés like "I am a passionate team player")
- Focused on what I bring to THEM, not what I want from the job
- Under 300 words

Job: {job.get('title')} at {job.get('company')}
Location: {job.get('location')}
Salary: {job.get('salary', 'not listed')}
Why it scored well: {job.get('explanation', '')}

Job description excerpt:
{job.get('description', '')[:1000]}

Candidate:
- Name: {name}
- Experience: {experience_years} years
- Skills: {skills}
- Target roles: {target_titles}
- Industries of interest: {industries_preferred}
- Background summary (from resume):
{base_resume[:600]}

Output only the cover note text. No subject line, no "Dear Hiring Manager" boilerplate unless it flows naturally.
"""
        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
