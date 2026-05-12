"""Resume tailoring — generates a job-specific resume variant via the configured AI provider."""

import os
from ai.client import complete_async


class ResumeTailor:
    async def tailor(self, job: dict, profile: dict) -> str:
        base_resume = profile.get("base_resume", "")
        skills = ", ".join(profile.get("skills", []))
        name = profile.get("name", "Candidate")

        prompt = (
            f"You are a professional resume writer.\n\n"
            f"I'm applying for: {job.get('title')} at {job.get('company')} ({job.get('location')})\n\n"
            f"Job description (excerpt):\n{job.get('description', '')[:1500]}\n\n"
            f"My background:\n"
            f"- Name: {name}\n"
            f"- Years of experience: {profile.get('experience_years', '')}\n"
            f"- Skills: {skills}\n"
            f"- Base resume:\n{base_resume}\n\n"
            f"Write a tailored, ATS-friendly resume for this specific job.\n"
            f"- Keep it to 1 page worth of content (under 600 words)\n"
            f"- Lead with a 2-sentence summary targeted at this role\n"
            f"- Reorder/reframe skills and experience to match the job description keywords\n"
            f"- Use plain text, no markdown headers with #\n"
            f"- Output only the resume content, nothing else"
        )
        return await complete_async(prompt, max_tokens=800)

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
