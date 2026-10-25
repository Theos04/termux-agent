// Save as: /data/data/com.termux/files/home/automation/chrome-launcher/scripts-library/naukri/extract_jobs_cleaned.js

(() => {
    'use strict';
    
    const jobCards = document.querySelectorAll('[data-job-id]');
    
    if (!jobCards.length) {
        return {
            success: false,
            error: 'No job cards found',
            timestamp: new Date().toISOString()
        };
    }
    
    const jobs = Array.from(jobCards).map((card, index) => {
        // Helper to clean text
        const clean = (text) => text?.trim()?.replace(/\s+/g, ' ') || '';
        
        // Get elements
        const titleEl = card.querySelector('p.title, .title');
        const companyEl = card.querySelector('.companyInfo .subTitle, .companyInfo, .company');
        const locationEl = card.querySelector('.loc, .location');
        const salaryEl = card.querySelector('.salary, .sal');
        const experienceEl = card.querySelector('.exp, .experience');
        const ratingEl = card.querySelector('.rating');
        const reviewsEl = card.querySelector('.reviewsCount');
        const postedEl = card.querySelector('.job-post-day, .posted, .date');
        
        // Extract skills (split by spaces or newlines)
        const skillElements = card.querySelectorAll('.skill, .tag');
        const skills = Array.from(skillElements)
            .map(el => clean(el.textContent))
            .filter(Boolean)
            .flatMap(s => s.split(/[\s,]+/))
            .filter(s => s.length > 2);
        
        // Get clean company name (remove rating and reviews)
        let company = clean(companyEl?.textContent) || '';
        company = company.split('Posted')[0].trim();
        company = company.replace(/[\d.]+ Reviews$/, '').trim();
        company = company.replace(/^[\d.]+$/, '').trim();
        
        // Extract salary (clean)
        let salary = clean(salaryEl?.textContent) || 'Not disclosed';
        if (salary === 'Not disclosed' || salary === 'Not Disclosed') {
            salary = 'Not disclosed';
        }
        
        // Get apply URL
        const applyLink = card.querySelector('a[href*="apply"]');
        const allLinks = Array.from(card.querySelectorAll('a')).map(a => ({
            text: clean(a.textContent),
            href: a.href
        })).filter(link => link.text || link.href);
        
        return {
            index: index + 1,
            jobId: card.dataset.jobId || '',
            title: clean(titleEl?.textContent) || '',
            company: company,
            location: clean(locationEl?.textContent) || '',
            salary: salary,
            experience: clean(experienceEl?.textContent) || '',
            rating: clean(ratingEl?.textContent) || '',
            reviews: clean(reviewsEl?.textContent) || '',
            posted: clean(postedEl?.textContent) || '',
            skills: skills.slice(0, 20), // Limit skills
            applyUrl: applyLink?.href || '',
            links: allLinks.slice(0, 5),
            description: clean(card.textContent).substring(0, 500)
        };
    });
    
    // Clean up data: remove duplicate companies, fix formatting
    const cleanedJobs = jobs.map(job => ({
        ...job,
        skills: [...new Set(job.skills)].filter(s => s.length > 2),
        // Extract numeric salary if possible
        salaryRange: job.salary.includes('-') ? job.salary : null
    }));
    
    // Statistics
    const stats = {
        totalJobs: cleanedJobs.length,
        withCompany: cleanedJobs.filter(j => j.company).length,
        withSalary: cleanedJobs.filter(j => j.salary && j.salary !== 'Not disclosed').length,
        withLocation: cleanedJobs.filter(j => j.location).length,
        withSkills: cleanedJobs.filter(j => j.skills.length > 0).length,
        uniqueCompanies: [...new Set(cleanedJobs.map(j => j.company).filter(Boolean))].length,
        averageSkills: cleanedJobs.reduce((acc, j) => acc + j.skills.length, 0) / cleanedJobs.length
    };
    
    // Top companies
    const companyCounts = {};
    cleanedJobs.forEach(job => {
        if (job.company) {
            companyCounts[job.company] = (companyCounts[job.company] || 0) + 1;
        }
    });
    const topCompanies = Object.entries(companyCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10)
        .map(([name, count]) => ({ name, count }));
    
    return {
        success: true,
        stats: stats,
        topCompanies: topCompanies,
        jobs: cleanedJobs,
        timestamp: new Date().toISOString(),
        url: window.location.href,
        totalJobCards: jobCards.length
    };
})();
