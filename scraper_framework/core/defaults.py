# core/defaults.py
"""Default scraper configurations for all partitions"""

from .models import ScraperConfig

# Default partition scrapers
DEFAULT_PARTITION = {
    'unstop_hackathons': ScraperConfig(
        name='unstop_hackathons',
        url='https://unstop.com/hackathons',
        schedule='0 */6 * * *',
        selectors={
            'hackathon_name': '.hackathon-card .title',
            'organizer': '.hackathon-card .organizer',
            'mode': '.hackathon-card .mode',
            'prize': '.hackathon-card .prize',
            'deadline': '.hackathon-card .deadline',
            'url': '.hackathon-card a:attr(href)'
        },
        extract_after_navigation=True,
        take_screenshot=True,
        save_html=True
    ),
    'unstop_jobs': ScraperConfig(
        name='unstop_jobs',
        url='https://unstop.com/jobs',
        schedule='0 */4 * * *',
        selectors={
            'job_title': '.job-card .title',
            'company': '.job-card .company',
            'location': '.job-card .location',
            'type': '.job-card .type',
            'deadline': '.job-card .deadline',
            'url': '.job-card a:attr(href)'
        },
        extract_after_navigation=True,
        take_screenshot=True,
        save_html=True
    ),
    'github_trending': ScraperConfig(
        name='github_trending',
        url='https://github.com/trending',
        schedule='0 */6 * * *',
        selectors={
            'repo_name': '.h3 a',
            'description': '.col-9 .text-gray',
            'language': '.f6 .repo-language-color + span',
            'stars': '.f6 a[href*="stargazers"]',
            'forks': '.f6 a[href*="forks"]',
            'url': '.h3 a:attr(href)'
        },
        extract_after_navigation=True,
        take_screenshot=True,
        save_html=True
    ),
    'indeed_jobs': ScraperConfig(
        name='indeed_jobs',
        url='https://www.indeed.com/jobs?q=python',
        schedule='0 */4 * * *',
        selectors={
            'job_title': '.jobTitle',
            'company': '.companyName',
            'location': '.companyLocation',
            'url': '.jcs-JobTitle:attr(href)'
        },
        extract_after_navigation=True,
        take_screenshot=True,
        save_html=True
    ),
}

# Production partition scrapers
PRODUCTION_PARTITION = {
    'linkedin_jobs': ScraperConfig(
        name='linkedin_jobs',
        url='https://www.linkedin.com/jobs/',
        schedule='0 */12 * * *',
        selectors={
            'job_title': '.job-card-list__title',
            'company': '.job-card-list__company-name',
            'location': '.job-card-list__location',
            'url': '.job-card-list a:attr(href)'
        },
        partition='production'
    ),
    'naukri_jobs': ScraperConfig(
        name='naukri_jobs',
        url='https://www.naukri.com/',
        schedule='0 */8 * * *',
        selectors={
            'job_title': '.jobTuple .title',
            'company': '.jobTuple .subTitle',
            'location': '.jobTuple .location',
            'salary': '.jobTuple .salary',
            'url': '.jobTuple a:attr(href)'
        },
        partition='production'
    ),
}

# Staging partition scrapers
STAGING_PARTITION = {
    'devfolio_hackathons': ScraperConfig(
        name='devfolio_hackathons',
        url='https://devfolio.co/hackathons',
        schedule='0 */12 * * *',
	        selectors={
            'hackathon_name': '.hackathon-card .name',
            'organizer': '.hackathon-card .organizer',
            'mode': '.hackathon-card .mode',
            'prize': '.hackathon-card .prize',
            'deadline': '.hackathon-card .deadline',
            'url': '.hackathon-card a:attr(href)'
        },
        partition='staging'
    ),
    'hackerearth_hackathons': ScraperConfig(
        name='hackerearth_hackathons',
        url='https://www.hackerearth.com/challenges/hackathon/',
        schedule='0 */12 * * *',
        selectors={
            'hackathon_name': '.challenge-card .challenge-name',
            'organizer': '.challenge-card .challenge-desc',
            'deadline': '.challenge-card .challenge-ends',
            'url': '.challenge-card a:attr(href)'
        },
        partition='staging'
    ),
}

# All defaults by partition
DEFAULT_SCRAPERS = {
    'default': DEFAULT_PARTITION,
    'production': PRODUCTION_PARTITION,
    'staging': STAGING_PARTITION,
}
