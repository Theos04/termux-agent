# test_intelligence.py - Quick test for Termux
from job_intelligence_termux import TermuxJobIntelligence

def test():
    print("🧠 Testing Termux Job Intelligence")
    print("=" * 40)
    
    # Initialize
    intel = TermuxJobIntelligence()
    
    # Load jobs
    if not intel.load_jobs():
        print("❌ No jobs found")
        return
    
    print(f"✅ Loaded {len(intel.jobs)} jobs")
    
    # Test embedding
    intel.embed_all_jobs()
    print(f"✅ Created {len(intel.job_embeddings)} embeddings")
    
    # Test analysis
    analysis = intel.analyze_market()
    print(f"\n📊 Market Stats:")
    print(f"   Total: {analysis['total_jobs']}")
    print(f"   Top Skills: {', '.join([s for s, _ in analysis['top_skills'][:5]])}")
    
    # Test matching
    skills = ["Python", "JavaScript", "SQL", "React"]
    matches = intel.match_skills_to_jobs(skills, n_results=3)
    print(f"\n🤝 Skill Matching Results:")
    for match in matches:
        print(f"   • {match['title']} at {match['company']}: {match['percentage']}%")
    
    # Test search
    results = intel.find_similar_jobs("Software Engineer Python", n_results=3)
    print(f"\n🔍 Similar Jobs:")
    for result in results:
        print(f"   • {result['title']} at {result['company']} (sim: {result['similarity']:.3f})")
    
    print("\n✅ All tests passed!")

if __name__ == "__main__":
    test()
