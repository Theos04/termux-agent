# job_intelligence_termux_final.py - Fixed data extraction
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
        self.job_embeddings = {}
        
    def load_jobs(self, jobs_file: Optional[str] = None) -> List[Dict]:
        """Load jobs from JSON file with better data extraction"""
        if not jobs_file:
            # Try processed details first
            detail_dir = Path("job_details")
            if detail_dir.exists():
                processed_files = sorted(detail_dir.glob("processed_details_*.json"), reverse=True)
                if processed_files:
                    jobs_file = processed_files[0]
                    print(f"📂 Using processed jobs from: {jobs_file}")
            
            if not jobs_file:
                # Try raw job details
                if detail_dir.exists():
                    raw_files = sorted(detail_dir.glob("all_details_*.json"), reverse=True)
                    if raw_files:
                        jobs_file = raw_files[0]
                        print(f"📂 Using raw jobs from: {jobs_file}")
            
            if not jobs_file:
                # Try scraped_data
                data_dir = Path("scraped_data")
                if data_dir.exists():
                    json_files = sorted(data_dir.glob("jobs_*.json"), reverse=True)
                    if json_files:
                        jobs_file = json_files[0]
                        print(f"📂 Using jobs from: {jobs_file}")
        
        if not jobs_file or not Path(jobs_file).exists():
            print(f"❌ No job file found. Run scraper first.")
            return []
        
        with open(jobs_file, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                self.jobs = data
            elif isinstance(data, dict) and 'jobs' in data:
                self.jobs = data['jobs']
            elif isinstance(data, dict) and 'job_details' in data:
                self.jobs = data['job_details']
            else:
                self.jobs = data
        
        # Clean and extract better data
        self._clean_job_data()
        print(f"📂 Loaded {len(self.jobs)} jobs")
        return self.jobs
    
    def _clean_job_data(self):
        """Clean and extract better data from jobs"""
        for job in self.jobs:
            # Extract company from various fields
            company = job.get('company') or job.get('company_name') or job.get('organization') or job.get('hiringOrganization')
            if isinstance(company, dict):
                company = company.get('name')
            if company:
                job['company'] = str(company).strip()
            
            # Extract location
            location = job.get('location') or job.get('job_location') or job.get('address')
            if isinstance(location, dict):
                # Try to get city/address from location dict
                location = location.get('addressLocality') or location.get('addressRegion') or location.get('streetAddress')
            if location:
                # Clean location string
                loc = str(location).strip()
                # Remove common prefixes
                loc = re.sub(r'^In Office\s*[|]\s*', '', loc)
                loc = re.sub(r'^Work from Home\s*[|]\s*', '', loc)
                job['location'] = loc
            
            # Extract salary
            salary = job.get('salary_range') or job.get('baseSalary') or job.get('salary')
            if isinstance(salary, dict):
                if 'value' in salary:
                    salary = salary['value']
                    if isinstance(salary, dict):
                        salary = salary.get('value')
            if salary:
                job['salary_range'] = str(salary)
            
            # Extract skills properly
            skills = job.get('skills', [])
            if isinstance(skills, str):
                skills = [s.strip() for s in skills.split(',')] if skills else []
            elif isinstance(skills, dict):
                # Extract from dict
                if 'skills' in skills:
                    skills = skills['skills']
                elif 'value' in skills:
                    skills = skills['value']
                if isinstance(skills, str):
                    skills = [s.strip() for s in skills.split(',')] if skills else []
                elif isinstance(skills, list):
                    skills = [str(s).strip() for s in skills]
                else:
                    skills = []
            elif not isinstance(skills, list):
                skills = []
            
            # Clean skills
            cleaned_skills = []
            for skill in skills:
                if skill and isinstance(skill, str):
                    # Split compound skills
                    for s in re.split(r'[,;|]', skill):
                        s = s.strip()
                        if s and len(s) > 1:
                            cleaned_skills.append(s)
            job['skills'] = list(set(cleaned_skills))  # Remove duplicates
            
            # Extract job type
            job_type = job.get('job_type') or job.get('employment_type')
            if job_type:
                job['job_type'] = str(job_type).strip()
            
            # Extract title
            title = job.get('title') or job.get('name') or job.get('job_title')
            if title:
                job['title'] = str(title).strip()
            
            # Extract description
            desc = job.get('description') or job.get('full_description') or job.get('job_description')
            if desc:
                if isinstance(desc, dict):
                    if 'text' in desc:
                        desc = desc['text']
                    else:
                        desc = str(desc)
                job['full_description'] = str(desc)
    
    def extract_keywords_with_weights(self, text: str) -> Dict[str, float]:
        """Extract keywords with weights from text"""
        text = text.lower()
        # Remove special characters
        text = re.sub(r'[^a-zA-Z0-9\s\-\.]', ' ', text)
        
        # Skill keywords with higher weights
        skill_weights = {
            # Programming/Technical
            'python': 2.0, 'java': 2.0, 'javascript': 2.0, 'typescript': 2.0,
            'react': 2.0, 'angular': 2.0, 'vue': 2.0, 'node': 2.0,
            'sql': 2.0, 'nosql': 2.0, 'mongodb': 2.0, 'postgresql': 2.0,
            'docker': 2.0, 'kubernetes': 2.0, 'aws': 2.0, 'azure': 2.0,
            'git': 1.5, 'linux': 1.5, 'devops': 2.0, 'ci/cd': 1.5,
            
            # Data/AI
            'machine learning': 2.0, 'deep learning': 2.0, 'nlp': 2.0,
            'data science': 2.0, 'analytics': 1.5, 'tableau': 1.5,
            'power bi': 1.5, 'excel': 1.5,
            
            # Business
            'business development': 1.8, 'sales': 1.5, 'marketing': 1.5,
            'customer support': 1.5, 'customer service': 1.5,
            'project management': 1.8, 'agile': 1.5, 'scrum': 1.5,
            
            # Soft Skills
            'leadership': 1.5, 'communication': 1.5, 'teamwork': 1.5,
            'problem solving': 1.5, 'critical thinking': 1.5,
            
            # Industry
            'supply chain': 1.5, 'inventory management': 1.5,
            'operations': 1.5, 'logistics': 1.5
        }
        
        # Stopwords
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'for', 'on', 'at', 'to', 'with',
                     'by', 'of', 'in', 'from', 'is', 'are', 'am', 'was', 'were', 'this',
                     'that', 'these', 'those', 'job', 'work', 'company', 'position',
                     'role', 'opportunity', 'looking', 'hiring', 'require', 'skills',
                     'years', 'experience', 'qualification', 'education', 'degree',
                     'about', 'above', 'across', 'after', 'against', 'among', 'around',
                     'before', 'behind', 'below', 'between', 'both', 'during', 'each',
                     'even', 'every', 'few', 'into', 'more', 'most', 'other', 'some',
                     'such', 'than', 'then', 'there', 'these', 'they', 'use', 'used',
                     'very', 'want', 'way', 'well', 'when', 'where', 'while', 'will',
                     'with', 'without', 'would', 'yes', 'yet', 'you', 'your'}
        
        words = text.split()
        word_weights = {}
        
        for word in words:
            if len(word) > 2 and word not in stopwords:
                # Check for multi-word skills
                base_weight = 1.0
                for skill, weight in skill_weights.items():
                    if skill in word or word in skill:
                        base_weight = weight
                        break
                
                word_weights[word] = word_weights.get(word, 0) + base_weight
        
        # Normalize
        max_weight = max(word_weights.values()) if word_weights else 1
        for word in word_weights:
            word_weights[word] = word_weights[word] / max_weight
        
        return word_weights
    
    def create_job_vector(self, job: Dict) -> Dict[str, float]:
        """Create a vector representation of a job"""
        text_parts = []
        
        # Title - high weight
        title = job.get('title', '')
        if title:
            text_parts.extend([title] * 3)
        
        # Skills - high weight
        skills = job.get('skills', [])
        if skills:
            text_parts.extend(skills)
        
        # Company
        company = job.get('company', '')
        if company:
            text_parts.append(company)
        
        # Location
        location = job.get('location', '')
        if location:
            text_parts.append(location)
        
        # Job type
        job_type = job.get('job_type', '')
        if job_type:
            text_parts.append(job_type)
        
        # Eligibility
        eligibility = job.get('eligibility', [])
        if isinstance(eligibility, str):
            eligibility = [eligibility] if eligibility else []
        if eligibility:
            text_parts.extend(eligibility)
        
        # Description (limited)
        description = job.get('full_description', '') or job.get('description', '')
        if description:
            desc = str(description)[:1000]
            text_parts.append(desc)
        
        # Combine
        text = ' '.join([str(p) for p in text_parts if p])
        return self.extract_keywords_with_weights(text)
    
    def cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Calculate cosine similarity between two vectors"""
        if not vec1 or not vec2:
            return 0
        
        common = set(vec1.keys()) & set(vec2.keys())
        if not common:
            return 0
        
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
            job_id = job.get('source_id') or job.get('url', '').split('/')[-1] or str(id(job))
            if job_id:
                vector = self.create_job_vector(job)
                self.job_embeddings[job_id] = vector
                
                # Store job metadata for quick access
                self.job_embeddings[f"{job_id}_title"] = job.get('title', 'Unknown')
                self.job_embeddings[f"{job_id}_company"] = job.get('company', 'Unknown')
                self.job_embeddings[f"{job_id}_location"] = job.get('location', 'Unknown')
        
        print(f"✅ Created embeddings for {len(self.job_embeddings)} entries")
        return len(self.job_embeddings)
    
    def find_similar_jobs(self, query: str, n_results: int = 10) -> List[Dict]:
        """Find similar jobs using text similarity"""
        if not self.job_embeddings:
            self.embed_all_jobs()
        
        query_vector = self.extract_keywords_with_weights(query)
        
        similarities = []
        for job_id, vector in self.job_embeddings.items():
            if '_' in job_id:
                continue
            
            sim = self.cosine_similarity(query_vector, vector)
            
            job = next((j for j in self.jobs if (j.get('source_id') or j.get('url', '').split('/')[-1]) == job_id), None)
            if job:
                similarities.append({
                    'job': job,
                    'similarity': sim,
                    'title': job.get('title', 'Unknown'),
                    'company': job.get('company', 'Unknown'),
                    'location': job.get('location', 'Unknown')
                })
        
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        return similarities[:n_results]
    
    def match_skills_to_jobs(self, skills: List[str], n_results: int = 10) -> List[Dict]:
        """Match candidate skills to jobs"""
        if not self.jobs:
            self.load_jobs()
        
        candidate_skills = [s.lower().strip() for s in skills if s]
        matches = []
        
        for job in self.jobs:
            job_skills = job.get('skills', [])
            if not job_skills:
                continue
            
            matched = []
            missing = []
            
            for job_skill in job_skills:
                job_skill_lower = job_skill.lower().strip()
                matched_skill = None
                
                for candidate_skill in candidate_skills:
                    if job_skill_lower in candidate_skill or candidate_skill in job_skill_lower:
                        matched_skill = candidate_skill
                        break
                
                if matched_skill:
                    matched.append(matched_skill)
                else:
                    missing.append(job_skill)
            
            total_skills = len(job_skills)
            if total_skills > 0:
                match_score = len(matched) / total_skills
            else:
                match_score = 0
            
            if match_score > 0:
                matches.append({
                    'job': job,
                    'title': job.get('title', 'Unknown'),
                    'company': job.get('company', 'Unknown'),
                    'location': job.get('location', 'Unknown'),
                    'score': match_score,
                    'percentage': round(match_score * 100, 1),
                    'matched_skills': list(set(matched)),
                    'missing_skills': list(set(missing))[:10]
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
            company = job.get('company')
            if company:
                analysis['companies'][company] += 1
            
            location = job.get('location')
            if location:
                analysis['locations'][location] += 1
            
            job_type = job.get('job_type')
            if job_type:
                analysis['job_types'][job_type] += 1
            
            skills = job.get('skills', [])
            for skill in skills:
                if skill and len(skill) > 1:
                    all_skills.append(skill)
                    analysis['skills'][skill] += 1
            
            salary = job.get('salary_range')
            if salary:
                nums = re.findall(r'(\d+(?:\.\d+)?)', str(salary))
                if nums:
                    try:
                        val = float(nums[0])
                        salaries.append(val)
                    except:
                        pass
        
        analysis['top_skills'] = analysis['skills'].most_common(20)
        analysis['companies_with_count'] = analysis['companies'].most_common()
        
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
        
        if analysis['companies']:
            report.append("🏢 TOP COMPANIES:")
            for company, count in analysis['companies'].most_common(10):
                report.append(f"   {company}: {count} jobs")
        report.append("")
        
        if analysis['locations']:
            report.append("📍 TOP LOCATIONS:")
            for location, count in analysis['locations'].most_common(10):
                report.append(f"   {location}: {count} jobs")
        report.append("")
        
        if analysis['job_types']:
            report.append("💼 JOB TYPES:")
            for jtype, count in analysis['job_types'].most_common(5):
                report.append(f"   {jtype}: {count} jobs")
        report.append("")
        
        if analysis['top_skills']:
            report.append("🔧 TOP SKILLS IN DEMAND:")
            for skill, count in analysis['top_skills'][:20]:
                report.append(f"   {skill}: {count} jobs")
        report.append("")
        
        if analysis['salary_stats']['jobs_with_salary'] > 0:
            report.append("💰 SALARY ANALYSIS:")
            report.append(f"   Jobs with salary data: {analysis['salary_stats']['jobs_with_salary']}")
            report.append(f"   Average Salary: ₹{analysis['salary_stats']['avg']:,.0f}")
            report.append(f"   Min Salary: ₹{analysis['salary_stats']['min']:,.0f}")
            report.append(f"   Max Salary: ₹{analysis['salary_stats']['max']:,.0f}")
        
        return '\n'.join(report)

def main():
    print("🧠 TERMUX JOB INTELLIGENCE")
    print("=" * 60)
    
    intelligence = TermuxJobIntelligence()
    
    if not intelligence.load_jobs():
        print("❌ No jobs found. Run scraper first.")
        return
    
    print("\n🔢 Creating job embeddings...")
    intelligence.embed_all_jobs()
    
    print("\n📊 Analyzing market...")
    analysis = intelligence.analyze_market()
    print(f"   Total: {analysis['total_jobs']} jobs")
    print(f"   Companies: {len(analysis['companies'])}")
    print(f"   Locations: {len(analysis['locations'])}")
    if analysis['top_skills']:
        print(f"   Top Skills: {', '.join([s for s, _ in analysis['top_skills'][:5]])}")
    
    report = intelligence.generate_report()
    print("\n" + report)
    
    report_dir = Path("job_details")
    report_dir.mkdir(exist_ok=True)
    report_file = report_dir / f"market_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w') as f:
        f.write(report)
    print(f"\n✅ Report saved to: {report_file}")
    
    print("\n🔍 Testing similarity search...")
    similar = intelligence.find_similar_jobs("Python Developer with React skills", n_results=3)
    for sim in similar:
        print(f"   • {sim['title']} at {sim['company']} ({sim['location']})")
        if sim['similarity'] > 0:
            print(f"     Similarity: {sim['similarity']:.3f}")
    
    print("\n🤝 Testing skill matching...")
    skills = ["Python", "SQL", "React", "Customer Support", "Business Development"]
    matches = intelligence.match_skills_to_jobs(skills, n_results=5)
    for match in matches:
        print(f"   • {match['title']} at {match['company']}: {match['percentage']}%")
        if match['matched_skills']:
            print(f"     ✅ {', '.join(match['matched_skills'][:3])}")

if __name__ == "__main__":
    main()
