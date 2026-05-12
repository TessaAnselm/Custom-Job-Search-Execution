"""Temporal activity: generate tailored resume and cover note for a job."""

import yaml
from temporalio import activity
from ai.resume_tailor import ResumeTailor
from ai.cover_note import CoverNoteGenerator


@activity.defn(name="generate_ai_docs")
async def generate_ai_docs(job: dict, profile_path: str) -> dict:
    with open(profile_path) as f:
        profile = yaml.safe_load(f)

    tailor = ResumeTailor()
    cover_gen = CoverNoteGenerator()

    resume_filename = ""
    cover_note = ""

    try:
        resume_filename = await tailor.tailor_and_save(job, profile)
        activity.logger.info(f"Resume saved: {resume_filename}")
    except Exception as e:
        activity.logger.error(f"Resume tailoring failed for {job.get('id')}: {e}")

    try:
        cover_note = await cover_gen.generate(job, profile)
        activity.logger.info(f"Cover note generated for {job.get('id')}")
    except Exception as e:
        activity.logger.error(f"Cover note generation failed for {job.get('id')}: {e}")

    return {
        "resume_filename": resume_filename,
        "cover_note": cover_note,
        "explanation": job.get("explanation", ""),
    }
