# PriceSync ZW-USD - Quick Start Guide

**Get up and running in 5 minutes!**

---

## 1️⃣ Installation (2 minutes)

### Option A: Using Python Directly

```bash
# Clone the repository
git clone https://github.com/yourusername/pricesync-zw-usd.git
cd pricesync-zw-usd

# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python pricesync_zw-usd.py
```

### Option B: Using Standalone Executable (Windows)
- Download `pricesync-setup.exe`
- Run installer
- Double-click PriceSync shortcut

---

## 2️⃣ First Login (30 seconds)

**Default Credentials:**
- Username: `admin`
- Password: `admin`

⚠️ **Important:** You'll be forced to change the password on first login. Use a strong password!

---

## 3️⃣ Quick Setup (1 minute)

### Step 1: Import Products
1. Click **"Products"** tab
2. Click **"Import CSV"**
3. Select your product file
   - Required columns: `id`, `name`, `usd_price`, `category`
4. Click **"Import"**

**Example CSV:**
```csv
id,name,usd_price,category
P001,Paracetamol 500mg,5.99,Pharmacy
P002,Antibacterial Soap,2.49,General
P003,Multivitamin,12.99,Pharmacy
```

### Step 2: Set Profit Margins
1. Click **"Settings"** tab
2. Set **"Default Margin"** (e.g., 10%)
3. Click **"Apply Settings"**

### Step 3: Check Exchange Rate
1. Go to **"Dashboard"**
2. Current USD-ZWG rate is displayed
3. Click **"Fetch Rate"** to update immediately

---

## 4️⃣ Using the Dashboard

### What You'll See:
```
┌─────────────────────────────────────────┐
│  CURRENT RATE: 1,240.50 ZWG/USD        │
│  Source: ZimRate API                    │
│  Updated: 14:30:25                      │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  RATE HISTORY (Last 10)                 │
│  1,240.50 ZWG - ZimRate      14:30      │
│  1,239.75 ZWG - RBZ GitHub   13:30      │
│  1,238.90 ZWG - ZimRate      12:30      │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  QUICK CONVERTER                        │
│  USD: [100.00]  →  12,405.00 ZWG       │
└─────────────────────────────────────────┘
```

---

## 5️⃣ Common Tasks

### Update Product Prices
1. **Dashboard** → **"Refresh Prices"**
   - All products recalculated automatically
   - Applies current exchange rate + margin

### Export Updated Prices
1. **Products** → **"Export to CSV"**
2. Choose output file location
3. File ready for POS system import

### View Price History
1. **Rates** → **"Rate History"**
2. See all fetched rates with timestamps
3. Analyze pricing trends

### Manual Rate Fetch
1. **Dashboard** → **"Fetch Rate Now"**
2. System tries multiple sources in order
3. Falls back automatically if source fails

---

## 6️⃣ Settings Explained

### Pricing Settings
| Setting | Purpose | Example |
|---------|---------|---------|
| **Default Margin** | Global profit markup | 10% |
| **Rounding Mode** | Price rounding strategy | None / Nearest 5 / Ceil 10 |
| **Markup Type** | Fixed or percentage | Percentage |

### User Management
- Create additional users
- Assign roles: Admin, Manager, Viewer
- Change passwords
- Suspend users if needed

---

## 7️⃣ Troubleshooting

### Problem: "Cannot connect to rate sources"
**Solution:**
1. Check internet connection
2. Try manual fetch (click "Fetch Rate Now")
3. System automatically tries 4 different sources
4. Check firewall/antivirus settings

### Problem: "Database is locked"
**Solution:**
1. Close all instances of PriceSync
2. Wait 30 seconds
3. Restart the application

### Problem: "Tkinter not found"
**Solution:**
```bash
# Windows
pip install tk

# macOS (using Homebrew)
brew install python-tk

# Linux
sudo apt-get install python3-tk
```

### Problem: "BeautifulSoup4 import error"
**Solution:**
```bash
pip install beautifulsoup4
```
(Optional - system still works without it)

---

## 8️⃣ Tips & Tricks

### 💡 Keyboard Shortcuts
- `Ctrl+Q` - Quit application
- `Ctrl+R` - Refresh rates
- `Tab` - Navigate between fields
- `Enter` - Confirm actions

### 📊 Data Tips
- **Always backup** your database before major changes
- Export rates monthly for records
- Keep product list updated
- Review user access regularly

### ⚡ Performance Tips
- Avoid importing >5000 products at once
- Run automatic fetching during off-hours
- Archive old rate history quarterly
- Clear browser cache if UI slow

### 🔒 Security Tips
- Change default password immediately
- Create unique passwords for users
- Never share admin password
- Disable unused user accounts
- Regular database backups

---

## 9️⃣ Integration with POS

### Setup Webhook (if your POS supports it)

1. **Settings** → **"POS Integration"**
2. Enter your POS endpoint:
   ```
   http://your-pos-system.com/api/prices
   ```
3. Click **"Test Connection"**
4. On success, prices auto-sync every 5 minutes

### Export Sync File (if no webhook)

1. **Products** → **"Write Sync File"**
2. JSON file created in:
   ```
   ~/.RatePriceSyncZW/pos_sync/
   ```
3. Your POS can monitor this folder
4. Import prices when file updates

---

## 🔟 Getting Help

### Documentation
- 📖 **README.md** - Full documentation
- 📋 **PROJECT_ANALYSIS.md** - Technical details
- 🔗 **GITHUB_SETUP.md** - Git instructions

### Report Issues
1. Click **"Help"** → **"Report Issue"**
2. Or visit GitHub Issues page
3. Include error message & steps to reproduce

### Contact Support
📧 Email: rudo.muchadei@example.com
📞 Phone: +263 78 530 1555

---

## Checklist: You're Ready to Go! ✅

- [ ] Installed Python 3.8+
- [ ] Ran `pip install -r requirements.txt`
- [ ] Started app with `python pricesync_zw-usd.py`
- [ ] Logged in with admin/admin
- [ ] Changed admin password
- [ ] Imported product list
- [ ] Set profit margins
- [ ] Fetched current rate
- [ ] Viewed dashboard
- [ ] Exported products to test

---

## Next Steps

1. **Add Users** - Create Manager and Viewer accounts
2. **Setup Backup** - Schedule automatic database backups
3. **Test Integration** - Connect to your POS system
4. **Train Staff** - Show team how to use system
5. **Monitor Performance** - Check metrics regularly

---

## Welcome! 🎉

You're now running an automated retail pricing system for Zimbabwe. 

**Need help?** Check the full README.md or contact support.

**Found a bug?** Report it on GitHub!

**Have ideas?** We'd love your feedback!

---

**PriceSync v2.0** - Making Zimbabwean Retail Smarter 🇿🇼
