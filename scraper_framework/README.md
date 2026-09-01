Here's the complete updated README.md:

```markdown
# Scraper Framework

A modular, multi-partition web scraping framework with Chrome automation and Celery support. Built for production-ready scraping with isolation, scalability, and ease of use.

## 🚀 Features

- **Multi-Partition Architecture** - Isolate scrapers by partition (default, production, staging, customer-specific)
- **🤖 Chrome Automation** - Uses CDP (Chrome DevTools Protocol) for reliable browser automation
- **📊 Multiple Storage Backends** - Google Sheets, Local JSON, S3 (extensible)
- **🔄 Celery Integration** - Distributed task execution with Redis/RabbitMQ
- **📡 REST API** - Full CRUD operations with aiohttp
- **💻 CLI Tool** - Complete command-line management interface
- **🏥 Health Checks** - Monitor scraper health and auto-recovery
- **🧹 Maintenance** - Automated cleanup of old results, screenshots, and HTML files
- **🔒 Thread-Safe** - Thread-safe registry with multi-partition support
- **📈 Statistics** - Track success rates, run counts, and performance metrics

## 📋 Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [CLI Commands](#cli-commands)
- [API Server](#api-server)
- [Celery Integration](#celery-integration)
- [Partitions](#partitions)
- [Storage](#storage)
- [Configuration](#configuration)
- [Development](#development)
- [License](#license)

## Installation

### Prerequisites

- Python 3.7+
- Redis (for Celery)
- Google Sheets API credentials (optional)
- Chrome/Chromium (for automation)

### Install from source

```bash
# Clone the repository
git clone <repository-url>
cd chrome-launcher

# Install in development mode
pip install -e .

# Install dependencies
pip install -r requirements.txt
```

### Quick Dependencies

```bash
pip install celery redis aiohttp google-sheets-db
```

## Quick Start

### 1. List available scrapers

```bash
python -m scraper_framework.cli list
```

### 2. Run a scraper

```bash
# Synchronous run
python -m scraper_framework.cli run unstop_hackathons

# Asynchronous run (via Celery)
python -m scraper_framework.cli run unstop_hackathons --async
```

### 3. Run all scrapers in a partition

```bash
python -m scraper_framework.cli run-all
```

### 4. Start the API server

```bash
python -m scraper_framework --mode api --port 8080
```

### 5. Start Celery worker

```bash
python -m scraper_framework --mode worker
```

## Architecture

The framework follows a modular, partition-based architecture:

```
scraper_framework/
├── core/           # Core components (registry, engine, models)
├── tasks/          # Celery tasks (scrapers, health, maintenance)
├── storage/        # Storage backends (Google Sheets, Local, S3)
├── api/            # REST API (routes, handlers, server)
├── cli/            # Command-line interface
├── config/         # Configuration (settings, logging)
├── schedulers/     # Celery Beat schedules
└── utils/          # Helper functions and validators
```

### Partition Architecture

Each partition is isolated with its own:
- Set of scrapers
- Storage backend
- Celery queues
- Concurrency settings
- Schedule configuration

## CLI Commands

### Global Options

```bash
python -m scraper_framework.cli [OPTIONS] COMMAND

Options:
  --partition PARTITION   Partition name (default: default)
  --format {json,table}   Output format (default: table)
```

### Commands

#### List Scrapers
```bash
# List all scrapers in default partition
python -m scraper_framework.cli list

# List scrapers in specific partition
python -m scraper_framework.cli --partition production list

# List all scrapers across all partitions
python -m scraper_framework.cli list --all

# List only active scrapers
python -m scraper_framework.cli list --active
```

#### Show Scraper Details
```bash
python -m scraper_framework.cli show unstop_hackathons
```

#### Run Scrapers
```bash
# Run a single scraper synchronously
python -m scraper_framework.cli run unstop_hackathons

# Run a single scraper asynchronously (Celery)
python -m scraper_framework.cli run unstop_hackathons --async

# Run all scrapers in a partition
python -m scraper_framework.cli run-all

# Run all scrapers in a partition asynchronously
python -m scraper_framework.cli run-all --async
```

#### Statistics
```bash
# Show statistics for default partition
python -m scraper_framework.cli stats

# Show statistics for specific partition
python -m scraper_framework.cli --partition production stats
```

#### Partitions
```bash
# List all partitions
python -m scraper_framework.cli partitions
```

#### Create Scraper
```bash
python -m scraper_framework.cli create \
    --name my_scraper \
    --url https://example.com \
    --selectors '{"title":".title", "price":".price"}'
```

#### Delete Scraper
```bash
python -m scraper_framework.cli delete my_scraper --force
```

#### Test Scraper
```bash
python -m scraper_framework.cli test unstop_hackathons
```

#### Results
```bash
# Show results for a scraper
python -m scraper_framework.cli results --scraper unstop_hackathons --limit 10
```

#### Export Configuration
```bash
python -m scraper_framework.cli export --file my_scrapers.json
```

## API Server

### Start the API Server

```bash
# Default partition
python -m scraper_framework --mode api --port 8080

# Specific partition
python -m scraper_framework --mode api --partition production --port 8080
```

### API Endpoints

```
GET     /                                   - API information
GET     /health                             - Health check
GET     /api/partitions/{partition}/scrapers - List scrapers
GET     /api/partitions/{partition}/scrapers/{name} - Get scraper
POST    /api/partitions/{partition}/scrapers - Create scraper
PUT     /api/partitions/{partition}/scrapers/{name} - Update scraper
DELETE  /api/partitions/{partition}/scrapers/{name} - Delete scraper
POST    /api/partitions/{partition}/scrapers/{name}/run - Run scraper
POST    /api/partitions/{partition}/scrapers/run-all - Run all scrapers
GET     /api/partitions/{partition}/results - Get results
GET     /api/partitions/{partition}/stats   - Get statistics
POST    /api/partitions/{partition}/scrape  - Scrape custom URL
```

### Example API Usage

```bash
# List scrapers
curl http://localhost:8080/api/partitions/default/scrapers

# Run a scraper
curl -X POST http://localhost:8080/api/partitions/default/scrapers/unstop_hackathons/run

# Create a scraper
curl -X POST http://localhost:8080/api/partitions/default/scrapers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test_scraper",
    "url": "https://example.com",
    "selectors": {"title": ".title"}
  }'
```

## Celery Integration

### Start Celery Worker

```bash
python -m scraper_framework --mode worker
```

### Celery Beat Scheduler

The framework includes pre-configured schedules for each partition:

```python
# schedulers/celery_beat.py
SCHEDULES = {
    'default_partition_scrapers': {
        'task': 'run_partition_scrapers',
        'schedule': crontab(minute=0, hour='*/6'),  # Every 6 hours
        'args': ('default',),
    },
    'production_partition_scrapers': {
        'task': 'run_partition_scrapers',
        'schedule': crontab(minute=0, hour='*/4'),  # Every 4 hours
        'args': ('production',),
    },
    # ... more schedules
}
```

### Available Celery Tasks

```python
# Run a single scraper
run_scheduled_scraper.delay('unstop_hackathons', 'default')

# Run all scrapers in a partition
run_partition_scrapers.delay('production')

# Run all scrapers across all partitions
run_all_partitions.delay()

# Health checks
health_check_partition.delay('default')
health_check_all.delay()

# Maintenance
run_maintenance.delay('default')
```

## Partitions

### Pre-configured Partitions

| Partition | Description | Queues | Concurrency |
|-----------|-------------|--------|-------------|
| `default` | Default scrapers | chrome_default | 2 |
| `production` | Production scrapers | chrome_prod, storage_prod | 4 |
| `staging` | Staging scrapers | chrome_staging | 2 |
| `testing` | Testing scrapers | chrome_test | 1 |
| `customer_a` | Customer A scrapers | chrome_cust_a | 2 |
| `customer_b` | Customer B scrapers | chrome_cust_b | 2 |

### Default Scrapers

#### Default Partition
- `unstop_hackathons` - Scrapes hackathons from Unstop (every 6 hours)
- `unstop_jobs` - Scrapes jobs from Unstop (every 4 hours)
- `github_trending` - Scrapes trending repos from GitHub (every 6 hours)

#### Production Partition
- `linkedin_jobs` - Scrapes jobs from LinkedIn (every 12 hours)
- `naukri_jobs` - Scrapes jobs from Naukri (every 8 hours)

#### Staging Partition
- `devfolio_hackathons` - Scrapes hackathons from Devfolio (every 12 hours)
- `hackerearth_hackathons` - Scrapes hackathons from HackerEarth (every 12 hours)

## Storage

### Google Sheets Storage

The framework integrates with Google Sheets for data storage:

```python
from scraper_framework.storage.google_sheets import GoogleSheetsStorage

storage = GoogleSheetsStorage(partition='default')
storage.save_result(result)
results = storage.get_results(scraper_name='unstop_hackathons', limit=100)
```

### Local Storage

For development or testing:

```python
from scraper_framework.storage.local import LocalStorage

storage = LocalStorage(partition='default', data_dir='data')
storage.save_result(result)
results = storage.get_results()
```

### Partition Storage Manager

Manage multiple storage backends:

```python
from scraper_framework.storage.partition_manager import PartitionStorageManager

manager = PartitionStorageManager()
manager.save_result(result, partition='production')
results = manager.get_results(partition='production')
```

## Configuration

### Partition Configuration

```python
# config/settings.py
PARTITIONS = {
    'default': PartitionConfig(
        name='default',
        queues=['chrome_default'],
        concurrency=2,
        scrapers=['unstop_hackathons', 'unstop_jobs'],
        storage='google_sheets'
    ),
    # ... more partitions
}
```

### Logging Configuration

Logs are stored in `logs/scraper_{partition}_{date}.log`:

```python
from scraper_framework.config.logging import setup_logging

logger = setup_logging(partition='default', level=logging.INFO)
```

## Development

### Running Tests

```bash
python -m pytest tests/
```

### Adding a New Scraper

1. **Define the scraper configuration:**

```python
from scraper_framework.core.models import ScraperConfig

config = ScraperConfig(
    name='my_scraper',
    url='https://example.com',
    schedule='0 */6 * * *',
    selectors={
        'title': '.title',
        'price': '.price',
    },
    partition='default'
)
```

2. **Add to registry:**

```python
from scraper_framework.core.registry import ScraperRegistry

registry = ScraperRegistry()
registry.add_scraper(config, partition='default')
```

3. **Run it:**

```bash
python -m scraper_framework.cli run my_scraper
```

### Adding a New Storage Backend

1. **Create storage class:**

```python
from scraper_framework.storage.base import BaseStorage

class MyStorage(BaseStorage):
    def save_result(self, result):
        # Implement save logic
        pass
    
    def get_results(self, scraper_name=None, limit=100):
        # Implement get results logic
        pass
```

2. **Register in partition manager:**

```python
# storage/partition_manager.py
if storage_type == 'my_storage':
    self.storages[partition] = MyStorage(partition)
```

## Troubleshooting

### Common Issues

1. **ModuleNotFoundError: No module named 'core.engine'**
   - Fix: Ensure you're using `from scraper_framework.core.engine import ScraperEngine`

2. **Celery TimeoutError**
   - Check if Redis is running: `redis-cli ping`
   - Start Celery worker: `python -m scraper_framework --mode worker`

3. **Google Sheets connection failed**
   - Verify credentials file exists in `~/.config/google-sheets-db/`
   - Share the sheet with the service account email

4. **CLI command not found**
   - Use the full command: `python -m scraper_framework.cli list`
   - Or create an alias: `alias scraper='python -m scraper_framework.cli'`

## License

MIT License

Copyright (c) 2024

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Contributing

Contributions are welcome! Please submit pull requests or open issues for bugs and feature requests.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Support

For questions and support:
- Open an issue on GitHub
- Check the documentation
- Contact the maintainers

---

**Built with ❤️ for reliable, scalable web scraping**
