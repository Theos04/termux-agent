(function() {
    'use strict';

    // Function to extract job listings and return as object
    function extractJobListings() {
        const listings = document.querySelectorAll('app-competition-listing');
        const jobs = [];

        listings.forEach((listing) => {
            const link = listing.querySelector('a.item');
            if (!link) return;

            const job = {
                title: link.querySelector('h3[itemprop="name"]')?.textContent?.trim() || 'N/A',
                company: link.querySelector('p.single-wrap')?.textContent?.trim() || 'N/A',
                location: link.querySelector('.job_location')?.textContent?.trim() || 'N/A',
                experience: 'N/A',
                jobType: 'N/A',
                salary: 'N/A',
                deadline: 'N/A',
                daysLeft: 'N/A',
                skills: [],
                url: link.getAttribute('href') || 'N/A'
            };

            // Extract experience
            const expElement = link.querySelector('.other_fields .ng-star-inserted');
            if (expElement) {
                const expText = expElement.textContent.trim();
                if (expText && (expText.includes('years') || expText.includes('experience'))) {
                    job.experience = expText;
                }
            }

            // Extract job type
            const typeElements = link.querySelectorAll('.other_fields span');
            typeElements.forEach(el => {
                const typeText = el.textContent.trim();
                if (typeText === 'Full Time' || typeText === 'Contractual/Temporary' || 
                    typeText.includes('Contractual')) {
                    job.jobType = typeText;
                }
            });

            // Extract salary
            const salaryElement = link.querySelector('.cash_widget .title');
            if (salaryElement) {
                job.salary = salaryElement.textContent.trim();
            }

            // Extract deadline and days left
            const tags = link.querySelectorAll('.left-fields un-tags .tag-text');
            tags.forEach((tag, idx) => {
                const text = tag.textContent.trim();
                if (idx === 0) {
                    job.deadline = text;
                } else if (idx === 1 && text.includes('days left')) {
                    job.daysLeft = text;
                }
            });

            // Extract skills
            link.querySelectorAll('.un-el-chip-content .chip_text').forEach(skill => {
                const skillText = skill.textContent.trim();
                if (skillText && !job.skills.includes(skillText)) {
                    job.skills.push(skillText);
                }
            });

            // Get featured status
            const featured = link.closest('app-featured-opportunity-tile') !== null;
            job.isFeatured = featured;

            jobs.push(job);
        });

        return {
            totalJobs: jobs.length,
            timestamp: new Date().toISOString(),
            jobs: jobs
        };
    }

    // Return the data
    return extractJobListings();
})();
