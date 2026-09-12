# PriceSync ZW-USD 📊

**Automated Exchange Rate & Retail Pricing System for Zimbabwe**

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Overview

PriceSync is an intelligent automation system that synchronizes USD-to-ZWG exchange rates and automatically updates retail pricing in real-time. Built specifically for Zimbabwe's dynamic pricing environment, it provides a multi-source rate retrieval system with a professional Tkinter UI and robust database management.

### Key Features

✨ **Multi-Source Rate Retrieval**
- Primary: ZimRate API
- Secondary: RBZ GitHub API
- Tertiary: RBZ Website Scraping
- Fallback: ZimPriceCheck API
- Automatic source switching on failure

🎯 **Intelligent Pricing Engine**
- Automatic USD → ZWG conversion
- Configurable profit margins (global & per-category)
- Multiple rounding strategies (none, nearest-5, ceil-10)
- Bulk product pricing in seconds

🔐 **Enterprise Security**
- User authentication with role-based access
- Admin/Manager/Viewer permission levels
- Password hashing with salt
- User activity logging
- Password change enforcement

📊 **Real-Time Monitoring**
- Live rate display dashboard
- Rate history tracking
- Performance metrics collection
- System uptime monitoring
- Fetch latency analysis

🔄 **POS/Inventory Integration**
- Webhook-based price synchronization
- JSON export for inventory systems
- File-based sync option
- CSV import/export capabilities

## Requirements

### System Requirements
- **Python**: 3.8 or higher
- **OS**: Windows, macOS, or Linux
- **RAM**: Minimum 512MB
- **Storage**: 100MB (includes database)

### Python Dependencies

```bash
pip install -r requirements.txt
```

**Core Dependencies:**
- `requests` - HTTP requests for API calls
- `openpyxl` - Excel file handling
- `beautifulsoup4` - Web scraping (optional)
- `tkinter` - Built-in GUI framework (usually pre-installed)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/pricesync-zw-usd.git
cd pricesync-zw-usd
```

### 2. Create Virtual Environment (Recommended)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Application

```bash
python pricesync_zw-usd.py
```

**Default Login:**
- Username: `admin`
- Password: `admin` (change on first login!)

## Usage Guide

### Dashboard
The main dashboard displays:
- Current USD-ZWG exchange rate
- Rate source and update time
- Last 10 rates history
- Quick currency converter
- System status indicators

### Product Management
1. **Import Products**: Load product list from CSV/Excel
   - Required columns: `id`, `name`, `usd_price`, `category`
2. **Set Margins**: Configure per-category or global profit margins
3. **Auto-Calculate**: System recalculates ZWG prices in real-time

### Pricing Settings
- **Default Margin**: Global markup percentage
- **Rounding Mode**:
  - None: Keep decimal values
  - Nearest 5: Round to nearest 5 ZWG
  - Ceil 10: Round up to nearest 10 ZWG
- **Markup Type**: Percentage or fixed amount

### Rate Synchronization
- **Auto Fetch**: Automatic rate updates (configurable interval)
- **Manual Fetch**: On-demand rate retrieval
- **Rate History**: View all historical rates
- **Source Status**: Monitor API availability

### User Management
- Create/edit/delete users
- Assign roles (Admin, Manager, Viewer)
- Force password changes
- Suspend/unsuspend users
- Audit user activity

## Architecture

### Core Modules

**RateService**
- Multi-source exchange rate retrieval
- Threaded background fetching
- Automatic fallback mechanism
- Latency tracking

**PricingEngine**
- USD to ZWG conversion
- Margin application (percentage/fixed)
- Intelligent rounding
- Bulk price calculation

**DatabaseManager**
- SQLite3 backend
- Product storage
- User management
- Rate history
- Audit logging

**IntegrationBridge**
- POS webhook integration
- File-based sync
- JSON payload formatting
- Error handling

**MetricsCollector**
- Performance logging
- Availability tracking
- Uptime monitoring
- Latency statistics

## Configuration

### Database Location
```
~/.RatePriceSyncZW/pricesync.db
```

### Log Files
```
~/.RatePriceSyncZW/system_metrics.log
~/.RatePriceSyncZW/pos_sync/
```

### Theme Customization
Edit color constants in the source:
```python
BG = "#0a0f0d"        # Background
ACCENT = "#4cff91"    # Primary color
DANGER = "#ff6b6b"    # Error/warning
```

## API Integration

### POS Webhook Format

```json
{
  "timestamp": "2024-01-15T14:30:00",
  "rate_usd_zwg": 1240.50,
  "products": [
    {
      "id": "SKU001",
      "name": "Product Name",
      "zwg_price": 12405.00
    }
  ]
}
```

### Webhook Configuration
Set webhook URL in Settings tab:
```
http://your-pos-system.com/api/prices
```

## Testing

Run included test suite:
```bash
python test_pricesync.py
```

Test coverage includes:
- Rate fetching from multiple sources
- Pricing calculations with various margins
- Database operations
- User authentication
- Data import/export

## Troubleshooting

### Issue: Cannot connect to rate sources
**Solution:** Check internet connection, verify APIs are accessible

### Issue: Database locked error
**Solution:** Restart application, check file permissions

### Issue: Tkinter import error
**Solution:** 
```bash
# Windows
pip install tk

# Ubuntu/Debian
sudo apt-get install python3-tk

# macOS
brew install python-tk
```

### Issue: BeautifulSoup4 not found (non-critical)
**Solution:** Install optional dependency
```bash
pip install beautifulsoup4
```

## Performance Metrics

Based on testing:
- **Rate Fetch Time**: 200-800ms (depending on source)
- **Bulk Price Calculation**: <100ms for 1000 products
- **Database Query**: <50ms average
- **Source Availability**: >95% (with multi-source fallback)

## Security Considerations

⚠️ **Important:**
1. **Change Default Password**: Admin password must be changed on first login
2. **HTTPS for Webhooks**: Always use HTTPS for POS webhook endpoints
3. **Database Backup**: Regular backups of `.db` file
4. **Access Control**: Restrict application access to authorized users
5. **API Keys**: Store any API keys in environment variables

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Support

For issues, questions, or suggestions:
- 📧 Email: rudo.muchadei@example.com
- 📞 Phone: +263 78 530 1555
- 🐛 GitHub Issues: [Create an issue](https://github.com/yourusername/pricesync-zw-usd/issues)

## Changelog

### v2.0
- Multi-source exchange rate system
- Enhanced pricing engine with rounding modes
- Role-based user authentication
- POS webhook integration
- Performance metrics collection
- Improved UI/UX with dark theme

### v1.0
- Initial release
- Basic rate fetching
- Simple pricing calculation

## Acknowledgments

- RBZ (Reserve Bank of Zimbabwe) for exchange rate data
- ZimRate API community
- Zimbabwe tech community for feedback and testing

---

**Rate-Price Sync v2.0** © 2024 - Automated Retail Pricing in Zimbabwe 🇿🇼
