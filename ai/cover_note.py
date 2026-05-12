"""Cover note generation — writes a personalized, non-templated cover note."""

from ai.client import complete_async


class CoverNoteGenerator:
    async def generate(self, job: dict, profile: dict) -> str:
        name = profile.get("name", "Candidate")
        skills = ", ".join(profile.get("skills", []))
        prompt = (
            f"You are a professional cover letter writer.\n\n"
            f"Write a cover note for this job application. It should be:\n"
            f"- 3-4 short paragraphs\n"
            f"- Specific to this company and role — not generic\n"
            f"- Honest and direct (no cliches like 'I am a passionate team player')\n"
            f"- Focused on what I bring to THEM, not what I want from the job\n"
            f"- Under 300 words\n\n"
            f"Job: {job.get('title')} at {job.get('company')}\n"
            f"Location: {job.get('location')}\n"
            f"Salary: {job.get('salary', 'not listed')}\n"
            f"Why it scored well: {job.get('explanation', '')}\n\n"
            f"Job description excerpt:\n{job.get('description', '')[:1000]}\n\n"
            f"Candidate:\n"
            f"- Name: {name}\n"
            f"- Experience: {profile.get('experience_years', '')} years\n"
            f"- Skills: {skills}\n"
            f"- Target roles: {', '.join(profile.get('target_titles', []))}\n"
            f"- Industries of interest: {', '.join(profile.get('industries', {}).get('preferred', []))}\n"
            f"- Background summary:\n{profile.get('base_resume', '')[:600]}\n\n"
            f"Output only the cover note text. No subject line or 'Dear Hiring Manager' boilerplate."
        )
        return await complete_async(prompt, max_tokens=500)
