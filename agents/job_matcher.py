def normalize(items):
    return {str(x).strip().lower() for x in items if str(x).strip()}

def recommend_jobs(candidate_skills, jobs):
    """Transparent baseline matcher; returns overlap-based scores, not AI claims."""
    candidate = normalize(candidate_skills)
    results = []
    for job in jobs:
        required = normalize(job.get("skills", "").split(","))
        matched = sorted(candidate & required)
        missing = sorted(required - candidate)
        score = round((len(matched) / len(required)) * 100) if required else 0
        results.append({
            "id": job["id"], "title": job["title"], "company": job["company"],
            "location": job["location"], "job_type": job["job_type"],
            "score": score, "matched_skills": matched, "missing_skills": missing,
            "description": job["description"]
        })
    return sorted(results, key=lambda x: (-x["score"], x["title"]))
