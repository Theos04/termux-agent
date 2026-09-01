// Save as: /data/data/com.termux/files/home/automation/chrome-launcher/scripts-library/naukri/extract_jobs.js

(() => {
    'use strict';
    
    // Find all job cards
    const jobCards = document.querySelectorAll('[data-job-id]');
    
    if (!jobCards.length) {
        return {
            error: 'No job cards found',
            totalJobs: 0,
            timestamp: new Date().toISOString()
        };
    }
    
    // Extract data from each job card
    const jobs = Array.from(jobCards).map((card, index) => {
        const titleEl = card.querySelector('p.title, .title');
        const companyEl = card.querySelector('.companyInfo .subTitle, .companyInfo, .company');
        const locationEl = card.querySelector('.loc, .location, [class*="loc"]');
        const salaryEl = card.querySelector('.salary, .sal, [class*="salary"], [class*="sal"]');
        const experienceEl = card.querySelector('.exp, .experience, [class*="exp"]');
        const ratingEl = card.querySelector('.rating, [class*="rating"]');
        const reviewsEl = card.querySelector('.reviewsCount, [class*="review"]');
        const postedEl = card.querySelector('.job-post-day, .posted, .date, [class*="post"]');
        const applyBtn = card.querySelector('a[href*="apply"], .apply, [class*="apply"]');
        
        // Extract skills
        const skillElements = card.querySelectorAll('.skill, .tag, [class*="skill"], [class*="tag"]');
        const skills = Array.from(skillElements).map(el => el.textContent.trim()).filter(Boolean);
        
        // Extract all links
        const links = Array.from(card.querySelectorAll('a')).map(a => ({
            text: a.textContent.trim(),
            href: a.href
        })).filter(link => link.text || link.href);
        
        return {
            index: index + 1,
            jobId: card.dataset.jobId || '',
            title: titleEl?.textContent?.trim() || '',
            company: companyEl?.textContent?.trim()?.split('Posted')[0]?.trim() || '',
            location: locationEl?.textContent?.trim() || '',
            salary: salaryEl?.textContent?.trim() || 'Not disclosed',
            experience: experienceEl?.textContent?.trim() || '',
            rating: ratingEl?.textContent?.trim() || '',
            reviews: reviewsEl?.textContent?.trim() || '',
            posted: postedEl?.textContent?.trim() || '',
            skills: skills,
            links: links,
            applyUrl: applyBtn?.href || links.find(l => l.href?.includes('apply'))?.href || '',
            description: card.textContent.trim().replace(/\s+/g, ' ').substring(0, 500)
        };
    });
    
    // Get statistics
    const stats = {
        totalJobs: jobs.length,
        withCompany: jobs.filter(j => j.company).length,
        withSalary: jobs.filter(j => j.salary && j.salary !== 'Not disclosed').length,
        withLocation: jobs.filter(j => j.location).length,
        withSkills: jobs.filter(j => j.skills.length > 0).length,
        uniqueCompanies: [...new Set(jobs.map(j => j.company).filter(Boolean))].length
    };
    
    // Return complete data
    return {
        stats: stats,
        jobs: jobs,
        timestamp: new Date().toISOString(),
        url: window.location.href,
        totalJobCards: jobCards.length
    };
})();
