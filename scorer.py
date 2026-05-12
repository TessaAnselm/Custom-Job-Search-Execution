"""
Job scorer — multi-factor weighted scoring of a job against the user profile.
Optionally uses OpenAI for richer explanation text.
"""

import os
import re
from openai import AsyncOpenAI


class JobScorer:
    def __init__(self, profile: dict):
        self.profile = profile
        self.weights = profile.get("scoring_weights", {
            "title_match": 0.30,
            "skills_match": 0.25,
            "salary_match": 0.20,
            "location_match": 0.15,
            "industry_match": 0.10,
        })
        self.openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def score(self, job: dict) -> dict:
        breakdown = {
            "title_match": self._score_title(job),
            "skills_match": self._score_skills(job),
            "salary_match": self._score_salary(job),
            "location_match": self._score_location(job),
            "industry_match": self._score_industry(job),
        }

        weighted = sum(
            breakdown[factor] * self.weights.get(factor, 0)
            for factor in breakdown
        )
        score = min(100, max(0, round(weighted)))

        explanation = await self._explain(job, score, breakdown)

        return {
            "score": score,
            "breakdown": breakdown,
            "explanation": explanation,
        }

    def _score_title(self, job: dict) -> float:
        """Score 0–100 based on title match to target titles."""
        title = job.get("title", "").lower()
        targets = [t.lower() for t in self.profile.get("target_titles", [])]

        for target in targets:
            if target in title or title in target:
                return 100.0
        # Partial keyword match
        keywords = set(" ".join(targets).split())
        job_words = set(title.split())
        overlap = keywords & job_words
        return min(100.0, len(overlap) / max(len(keywords), 1) * 100)

    def _score_skills(self, job: dict) -> float:
        """Score based on skill overlap between job description and profile."""
        description = (job.get("description", "") + " " + job.get("title", "")).lower()
        profile_skills = [s.lower() for s in self.profile.get("skills", [])]

        if not profile_skills:
            return 50.0

        matches = sum(1 for skill in profile_skills if skill in description)
        return min(100.0, matches / len(profile_skills) * 100)

    def _score_salary(self, job: dict) -> float:
        """Score salary against profile minimum and target."""
        salary_str = job.get("salary", "") or ""
        numbers = re.findall(r"\d[\d,]*", salary_str.replace(",", ""))
        if not numbers:
            return 50.0  # Unknown salary — neutral score

        salary_nums = [int(n) for n in numbers]
        # Use the higher end of any range
        max_salary = max(salary_nums)
        # Normalize: could be hourly or annual
        if max_salary < 500:
            max_salary *= 2000  # rough hourly → annual

        minimum = self.profile.get("salary", {}).get("minimum", 0)
        target = self.profile.get("salary", {}).get("target", minimum * 1.3)

        if max_salary < minimum:
            return 0.0
        if max_salary >= target:
            return 100.0
        return ((max_salary - minimum) / (target - minimum)) * 100

    def _score_location(self, job: dict) -> float:
        """Score location match."""
        location = job.get("location", "").lower()
        preferred = [l.lower() for l in self.profile.get("location", {}).get("preferred", [])]
        hard_no = [l.lower() for l in self.profile.get("location", {}).get("hard_no", [])]

        for no in hard_no:
            if no in location:
                return 0.0

        if "remote" in preferred and ("remote" in location or "anywhere" in location):
            return 100.0

        for pref in preferred:
            if pref in location:
                return 100.0

        return 20.0  # Located somewhere but not preferred

    def _score_industry(self, job: dict) -> float:
        """Score industry/company preference."""
        company_info = (job.get("company", "") + " " + job.get("description", "")).lower()
        preferred = [i.lower() for i in self.profile.get("industries", {}).get("preferred", [])]
        avoid = [i.lower() for i in self.profile.get("industries", {}).get("avoid", [])]

        for bad in avoid:
            if bad in company_info:
                return 0.0

        for good in preferred:
            if good in company_info:
                return 100.0

        return 50.0  # Neutral

    async def _explain(self, job: dict, score: int, breakdown: dict) -> str:
        """Use OpenAI to generate a human-readable explanation of the match."""
        try:
            prompt = f"""
You are helping someone evaluate a job posting. Given the scoring breakdown, write a 2-3 sentence
explanation of WHY this job scores {score}/100 for this candidate. Be specific and honest.
Focus on what's good and what's lacking. Keep it under 100 words.

Job: {job.get('title')} at {job.get('company')} ({job.get('location')})
Salary: {job.get('salary', 'not listed')}
Score breakdown: {breakdown}
Profile skills: {self.profile.get('skills', [])}
Target titles: {self.profile.get('target_titles', [])}
"""
            response = await self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            # Fallback to rule-based explanation
            top_factor = max(breakdown, key=breakdown.get)
            return f"Score {score}/100. Strongest signal: {top_factor.replace('_', ' ')} ({breakdown[top_factor]:.0f}/100)."
