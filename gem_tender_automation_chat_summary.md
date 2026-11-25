# GeM Tender Automation — Chat Summary

## Objective
Automate finding relevant tenders on GeM so the company does not have to manually go through many irrelevant bids. The user selects parameters, and the system displays suitable tenders in a sheet with a summary and important information from each tender.

## Tender categories

### IT tenders
- Software
- Website development
- Mobile app development
- Hardware
- Laptop and desktop
- Networking
- CCTV
- Server
- Cloud
- Cybersecurity
- AMC
- IT manpower
- Data entry
- ERP

### Other tenders
- Digital marketing
- Social media management
- Media management
- Content writing
- Graphic design
- Video production
- Printing
- Branding
- Event management
- Photography

The company mainly looks for IT tenders but may also consider smaller tenders in other areas that it can fulfil.

## Parameters to configure
The system should ask the user for all required parameters instead of hardcoding them.

Suggested starting values discussed:
- Region: All India
- Maximum IT tender value: ₹25 lakh
- Maximum other tender value: ₹5 lakh
- Maximum EMD: ₹50,000
- Minimum time remaining before closing: 7 days
- Exclude keywords: construction, civil, furniture, vehicle hire, security guards

Other discussed filters:
- Keywords and categories
- State or region
- Ministry or department
- Bid type (product or service)
- Estimated value
- Closing date
- EMD

## Tender matching
Use a scoring system rather than relying only on strict filters:
- Give points for relevant keyword matches.
- Give extra points for preferred locations and affordable EMD/value.
- Reduce the score for requirements the company cannot fulfil, such as heavy construction, civil work or high turnover requirements.
- Sort tenders by score.

## Information shown for each tender
- Bid number and link
- Item and quantity
- Buyer department and state
- Start date and end date
- Bid opening date
- EMD and estimated value
- Offer validity
- A 2–3 line summary
- Eligibility points to check:
  - Experience
  - Turnover
  - MSE or startup relaxation
  - OEM or authorization requirements

The system should read the tender PDF to extract important details and create the summary.

## Google Sheets
The proposed setup is to use a Settings tab in Google Sheets where the user can edit:
- IT and other keywords
- States or All India
- Maximum bid value and EMD
- Minimum days remaining
- Excluded keywords

The results would be written to Google Sheets.

## Technology discussed

| Part | Technology |
|---|---|
| Fetch bids | Python + `requests` |
| Browser fallback if blocked | Playwright |
| Read tender PDFs | `pdfplumber` |
| AI summaries | Groq API (free tier) |
| Output and settings | Google Sheets with `gspread` |
| Run | GitHub Actions, manual trigger |

## Manual execution
The workflow will use GitHub Actions `workflow_dispatch`. The user will open Actions and click **Run workflow**. There will be no scheduled or automatic daily run.

## Setup requirements discussed
1. Create a Google service account and share the Google Sheet with it.
2. Get a Groq API key.
3. Add the credentials as GitHub Secrets rather than storing them in code.

## Points discussed but not finalized
- Whether to use Google Sheets settings or a Streamlit form. Google Sheets was recommended as the simpler option, but the user had not confirmed the choice.
- Exact keywords, region, and final value limits were not finalized; the suggested values above were starting suggestions.
