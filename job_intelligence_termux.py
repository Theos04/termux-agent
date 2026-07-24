# job_intelligence_termux.py - Pure Python, Termux-compatible
import json
import re
import math
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import Counter, defaultdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TermuxJobIntelligence:
    """Job intelligence system optimized for Termux (no numpy)"""
    
    def __init__(self):
        self.jobs = []
        self.skill_embeddings = {}  # Manual embedding storage
        self.job_embeddings = {}    # Store job vectors as dictionaries
        
    def load_jobs(self, jobs_file: Optional[str] = None) -> List[Dict]:
        """Load jobs from JSON file"""
        if not jobs_file:
            # Try to find the latest processed jobs file
            detail_dir = Path("job_details")
            if detail_dir.exists():
                processed_files = sorted(detail_dir.glob("processed_details_*.json"), reverse=True)
                if processed_files:
                    jobs_file = processed_files[0]
            
            if not jobs_file:
                # Try scraped_data
                data_dir = Path("scraped_data")
                if data_dir.exists():
                    json_files = sorted(data_dir.glob("jobs_*.json"), reverse=True)
                    if json_files:
                        jobs_file = json_files[0]
        
        if not jobs_file or not Path(jobs_file).exists():
            print(f"❌ No job file found. Run scraper first.")
            return []
        
        with open(jobs_file, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                self.jobs = data
            elif isinstance(data, dict) and 'jobs' in data:
                self.jobs = data['jobs']
            else:
                self.jobs = data
        
        print(f"📂 Loaded {len(self.jobs)} jobs")
        return self.jobs
    
    def extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text (simple NLP without numpy)"""
        # Clean text
        text = text.lower()
        text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
        
        # Common stopwords
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'for', 'on', 'at', 'to', 'with',
                     'by', 'of', 'in', 'from', 'is', 'are', 'am', 'was', 'were', 'this',
                     'that', 'these', 'those', 'job', 'work', 'company', 'position',
                     'role', 'opportunity', 'looking', 'hiring', 'require', 'skills'}
        
        words = text.split()
        keywords = []
        for word in words:
            if len(word) > 2 and word not in stopwords:
                keywords.append(word)
        
        return keywords[:20]  # Limit to top 20
    
    def create_job_vector(self, job: Dict) -> Dict[str, float]:
        """Create a simple vector representation of a job (TF-IDF style)"""
        # Get text from job
        text_parts = [
            job.get('title', ''),
            job.get('company', ''),
            job.get('location', ''),
            job.get('job_type', ''),
            ' '.join(job.get('skills', [])),
            job.get('full_description', '')[:500]
        ]
        text = ' '.join([p for p in text_parts if p])
        
        # Extract keywords
        keywords = self.extract_keywords(text)
        
        # Create frequency vector
        vector = {}
        for keyword in keywords:
            vector[keyword] = vector.get(keyword, 0) + 1
        
        # Normalize (simple max normalization)
        max_freq = max(vector.values()) if vector else 1
        for key in vector:
            vector[key] = vector[key] / max_freq
        
        return vector
    
    def cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Calculate cosine similarity between two vectors (no numpy)"""
        if not vec1 or not vec2:
            return 0
        
        # Find common keys
        common = set(vec1.keys()) & set(vec2.keys())
        if not common:
            return 0
        
        # Calculate dot product and magnitudes
        dot_product = sum(vec1[k] * vec2[k] for k in common)
        
        mag1 = math.sqrt(sum(v * v for v in vec1.values()))
        mag2 = math.sqrt(sum(v * v for v in vec2.values()))
        
        if mag1 == 0 or mag2 == 0:
            return 0
        
        return dot_product / (mag1 * mag2)
    
    def embed_all_jobs(self) -> int:
        """Create embeddings for all jobs"""
        if not self.jobs:
            self.load_jobs()
        
        for job in self.jobs:
            job_id = job.get('source_id') or job.get('url', '').split('/')[-1]
            if job_id:
                self.job_embeddings[job_id] = self.create_job_vector(job)
        
        print(f"✅ Created embeddings for {len(self.job_embeddings)} jobs")
        return len(self.job_embeddings)
    
    def find_similar_jobs(self, query: str, n_results: int = 10) -> List[Dict]:
        """Find similar jobs using text similarity"""
        if not self.job_embeddings:
            self.embed_all_jobs()
        
        # Create query vector
        query_vector = self.create_job_vector({'full_description': query, 'title': query})
        
        # Calculate similarity with all jobs
        similarities = []
        for job_id, vector in self.job_embeddings.items():
            sim = self.cosine_similarity(query_vector, vector)
            
            # Find the job data
            job = next((j for j in self.jobs if (j.get('source_id') or j.get('url', '').split('/')[-1]) == job_id), None)
            if job:
                similarities.append({
                    'job': job,
                    'similarity': sim,
                    'title': job.get('title', 'Unknown'),
                    'company': job.get('company', 'Unknown')
                })
        
        # Sort by similarity
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        return similarities[:n_results]
    
    def match_skills_to_jobs(self, skills: List[str], n_results: int = 10) -> List[Dict]:
        """Match candidate skills to jobs"""
        if not self.jobs:
            self.load_jobs()
        
        candidate_skills = [s.lower() for s in skills]
        matches = []
        
        for job in self.jobs:
            job_skills = job.get('skills', [])
            if isinstance(job_skills, str):
                job_skills = [s.strip() for s in job_skills.split(',')] if job_skills else []
            job_skills = [s.lower() for s in job_skills]
            
            if not job_skills:
                continue
            
            # Calculate match
            matched = set(candidate_skills) & set(job_skills)
            match_score = len(matched) / len(set(job_skills)) if job_skills else 0
            
            if match_score > 0:
                matches.append({
                    'job': job,
                    'title': job.get('title', 'Unknown'),
                    'company': job.get('company', 'Unknown'),
                    'score': match_score,
                    'percentage': round(match_score * 100, 1),
                    'matched_skills': list(matched),
                    'missing_skills': list(set(job_skills) - set(candidate_skills))[:10]
                })
        
        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches[:n_results]
    
    def analyze_market(self) -> Dict[str, Any]:
        """Analyze job market trends"""
        if not self.jobs:
            self.load_jobs()
        
        analysis = {
            'total_jobs': len(self.jobs),
            'companies': Counter(),
            'locations': Counter(),
            'job_types': Counter(),
            'skills': Counter(),
            'top_skills': [],
            'companies_with_count': [],
            'salary_stats': {'avg': None, 'min': None, 'max': None, 'jobs_with_salary': 0}
        }
        
        all_skills = []
        salaries = []
        
        for job in self.jobs:
            # Companies
            company = job.get('company')
            if company:
                analysis['companies'][company] += 1
            
            # Locations
            location = job.get('location', '')
            if location:
                loc = location.split('|')[0].strip() if '|' in location else location
                analysis['locations'][loc] += 1
            
            # Job types
            job_type = job.get('job_type')
            if job_type:
                analysis['job_types'][job_type] += 1
            
            # Skills
            skills = job.get('skills', [])
            if isinstance(skills, str):
                skills = [s.strip() for s in skills.split(',')] if skills else []
            elif not isinstance(skills, list):
                skills = []
            
            for skill in skills:
                if skill and len(skill) > 1:
                    all_skills.append(skill)
                    analysis['skills'][skill] += 1
            
            # Salary
            salary = job.get('salary_range')
            if salary:
                nums = re.findall(r'(\d+(?:\.\d+)?)', salary)
                if nums:
                    try:
                        val = float(nums[0])
                        if 'LPA' in salary or 'Lakh' in salary:
                            val *= 100000
                        elif 'K' in salary or 'Thousand' in salary:
                            val *= 1000
                        salaries.append(val)
                    except:
                        pass
        
        # Top skills
        analysis['top_skills'] = analysis['skills'].most_common(20)
        analysis['companies_with_count'] = analysis['companies'].most_common()
        
        # Salary stats
        if salaries:
            analysis['salary_stats']['jobs_with_salary'] = len(salaries)
            analysis['salary_stats']['min'] = min(salaries)
            analysis['salary_stats']['max'] = max(salaries)
            analysis['salary_stats']['avg'] = sum(salaries) / len(salaries)
        
        return analysis
    
    def generate_report(self) -> str:
        """Generate a market report"""
        analysis = self.analyze_market()
        
        report = []
        report.append("=" * 70)
        report.append("📊 UNSTOP JOB MARKET REPORT")
        report.append("=" * 70)
        report.append(f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"📈 Total Jobs Analyzed: {analysis['total_jobs']}")
        report.append("")
        
        # Top Companies
        report.append("🏢 TOP 10 COMPANIES:")
        for company, count in analysis['companies'].most_common(10):
            report.append(f"   {company}: {count} jobs")
        report.append("")
        
        # Top Locations
        report.append("📍 TOP 10 LOCATIONS:")
        for location, count in analysis['locations'].most_common(10):
            report.append(f"   {location}: {count} jobs")
        report.append("")
        
        # Job Types
        report.append("💼 JOB TYPES:")
        for jtype, count in analysis['job_types'].most_common(5):
            report.append(f"   {jtype}: {count} jobs")
        report.append("")
        
        # Top Skills
        report.append("🔧 TOP 20 SKILLS:")
        for skill, count in analysis['top_skills'][:20]:
            report.append(f"   {skill}: {count} jobs")
        report.append("")
        
        # Salary
        if analysis['salary_stats']['jobs_with_salary'] > 0:
            report.append("💰 SALARY ANALYSIS:")
            report.append(f"   Jobs with salary data: {analysis['salary_stats']['jobs_with_salary']}")
            report.append(f"   Average Salary: ₹{analysis['salary_stats']['avg']:,.0f}")
            report.append(f"   Min Salary: ₹{analysis['salary_stats']['min']:,.0f}")
            report.append(f"   Max Salary: ₹{analysis['salary_stats']['max']:,.0f}")
        
        return '\n'.join(report)

def main():
    """Main function"""
    print("🧠 TERMUX JOB INTELLIGENCE")
    print("=" * 60)
    
    # Initialize
    intelligence = TermuxJobIntelligence()
    
    # Load jobs
    if not intelligence.load_jobs():
        print("❌ No jobs found. Run scraper first.")
        return
    
    # Create embeddings
    print("\n🔢 Creating job embeddings...")
    intelligence.embed_all_jobs()
    
    # Analyze market
    print("\n📊 Analyzing market...")
    analysis = intelligence.analyze_market()
    print(f"   Total: {analysis['total_jobs']} jobs")
    print(f"   Top Skills: {', '.join([s for s, _ in analysis['top_skills'][:5]])}")
    
    # Generate report
    report = intelligence.generate_report()
    print("\n" + report)
    
    # Save report
    report_dir = Path("job_details")
    report_dir.mkdir(exist_ok=True)
    report_file = report_dir / f"market_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w') as f:
        f.write(report)
    print(f"\n✅ Report saved to: {report_file}")
    
    # Demo similarity search
    print("\n🔍 Testing similarity search...")
    similar = intelligence.find_similar_jobs("Python Developer with React skills", n_results=3)
    for sim in similar:
        print(f"   • {sim['title']} at {sim['company']} (similarity: {sim['similarity']:.3f})")
    
    # Demo skill matching
    print("\n🤝 Testing skill matching...")
    skills = ["Python", "JavaScript", "SQL", "React", "Docker"]
    matches = intelligence.match_skills_to_jobs(skills, n_results=3)
    for match in matches:
        print(f"   • {match['title']} at {match['company']}: {match['percentage']}% match")

if __name__ == "__main__":
    main()
