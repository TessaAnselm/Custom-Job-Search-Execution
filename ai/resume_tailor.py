"""Resume tailoring — generates a job-specific resume variant via OpenAI."""

import os
import yaml
from openai import AsyncOpenAI


class ResumeTailor:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    async def tailor(self, job: dict, profile: dict) -> str:
        """
        Returns a plain-text tailored resume for this job.
        Caller is responsible for saving it to disk.
        """
        base_resume = profile.get("base_resume", "")
        skills = ", ".join(profile.get("skills", []))
        experience_years = profile.get("experience_years", "")
        name = profile.get("name", "Candidate")

        prompt = f"""You are a professional resume writer.

I'm applying for: {job.get('title')} at {job.get('company')} ({job.get('location')})

Job description (excerpt):
{job.get('description', '')[:1500]}

My background:
- Name: {name}
- Years of experience: {experience_years}
- Skills: {skills}
- Base resume:
{base_resume}

Write a tailored, ATS-friendly resume for this specific job.
- Keep it to 1 page worth of content (under 600 words)
- Lead with a 2-sentence summary targeted at this role
- Reorder/reframe skills and experience to match the job description keywords
- Use plain text, no markdown headers with #
- Output only the resume content, nothing else
"""
        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()

    async def tailor_and_save(self, job: dict, profile: dict, output_dir: str = "resumes") -> str:
        """Tailor and write to disk. Returns the filename."""
        os.makedirs(output_dir, exist_ok=True)
        content = await self.tailor(job, profile)
        safe_company = "".join(c if c.isalnum() else "_" for c in job.get("company", "company"))
        safe_title = "".join(c if c.isalnum() else "_" for c in job.get("title", "role"))
        filename = f"{output_dir}/resume_{safe_company}_{safe_title}_{job.get('id', '')[:6]}.txt"
        with open(filename, "w") as f:
            f.write(content)
        return filename
