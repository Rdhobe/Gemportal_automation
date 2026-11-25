"""Offline demo dataset shaped like the GeM bid-listing API.

The sample keeps dates relative to today so the demo stays useful. It is used
when the live GeM endpoint is unreachable, when ``GEM_SAMPLE_MODE=true``, or
when the user explicitly ticks "Use sample data".
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def _fmt(moment: datetime) -> str:
    return moment.strftime("%d-%m-%Y %I:%M %p")


def _row(
    index: int,
    title: str,
    category: str,
    department: str,
    ministry: str,
    state: str,
    value: int,
    emd: int,
    closes_in_days: int,
    quantity: str = "1",
    bid_type: str = "Service",
    offer_validity: str = "30 Days",
) -> dict[str, Any]:
    now = datetime.now()
    start = now - timedelta(days=6)
    end = now + timedelta(days=closes_in_days, hours=2)
    opening = end + timedelta(hours=3)
    bid_number = f"GEM/2026/B/{4200000 + index}"
    return {
        "b_id": f"9{index:09d}",
        "b_bid_number": bid_number,
        "b_category_name": category,
        "b_item_category": title,
        "b_total_quantity": quantity,
        "b_start_date": _fmt(start),
        "b_end_date": _fmt(end),
        "b_opening_date": _fmt(opening),
        "b_estimated_bid_value": f"{value:,}.00",
        "b_emd": f"{emd:,}.00",
        "b_bid_type": bid_type,
        "b_offer_validity": offer_validity,
        "ba_official_details_deptName": department,
        "ba_official_details_minName": ministry,
        "ba_official_details_state": state,
        "ba_official_details_city": state,
        "detail_url": f"https://bidplus.gem.gov.in/showbidDocument/9{index:09d}",
    }


def sample_bids() -> list[dict[str, Any]]:
    rows = [
        # --- IT tenders that should match -------------------------------------
        ("Supply of Laptops and Desktop Computers", "Laptop & Desktop", "Directorate of Higher Education", "Ministry of Education", "Delhi", 2_400_000, 48_000, 14, "120 Nos", "Product"),
        ("Development of Website and Web Portal for Municipal Services", "Website Development", "Municipal Corporation of Pune", "Ministry of Housing and Urban Affairs", "Maharashtra", 850_000, 0, 11, "1 Project"),
        ("Cloud Migration and Managed Cloud Services", "Cloud", "National Informatics Centre", "Ministry of Electronics and IT", "Karnataka", 2_200_000, 44_000, 18, "1 Project"),
        ("Comprehensive AMC for Computers and Printers", "AMC", "District Collectorate Office", "Ministry of Home Affairs", "Gujarat", 480_000, 9_600, 10, "1 Year"),
        ("Cybersecurity Audit and VAPT Services", "Cybersecurity", "State Bank Services Corporation", "Ministry of Finance", "Maharashtra", 1_000_000, 20_000, 16, "1 Project"),
        ("ERP Implementation and Support Services", "ERP", "Kerala State Industrial Development Corp", "Ministry of Commerce and Industry", "Kerala", 2_450_000, 49_000, 21, "1 Project"),
        ("Supply, Installation and Maintenance of CCTV Cameras", "CCTV", "Smart City Development Ltd", "Ministry of Housing and Urban Affairs", "Madhya Pradesh", 1_200_000, 24_000, 9, "1 Lot", "Product"),
        ("Annual Maintenance of Server Room and Networking Equipment", "Networking", "Indian Institute of Technology", "Ministry of Education", "Tamil Nadu", 600_000, 12_000, 13, "1 Year"),
        ("Design and Development of a Mobile Application", "Mobile App Development", "Department of Tourism", "Ministry of Tourism", "Rajasthan", 1_400_000, 28_000, 17, "1 Project"),
        ("Data Entry and Digitisation of Records", "Data Entry", "Registrar General of India", "Ministry of Home Affairs", "Uttar Pradesh", 300_000, 0, 12, "1 Project"),
        ("IT Manpower Services for Helpdesk Support", "IT Manpower", "Bharat Sanchar Nigam Limited", "Ministry of Communications", "West Bengal", 2_000_000, 40_000, 20, "1 Year"),
        ("Procurement of Servers and Storage", "Server", "Indian Space Research Organisation", "Department of Space", "Karnataka", 2_300_000, 46_000, 19, "1 Lot", "Product"),
        ("Supply of Network Switches and Routers", "Networking", "National Health Mission", "Ministry of Health and Family Welfare", "Assam", 650_000, 13_000, 8, "1 Lot", "Product"),
        ("Cloud-Based Attendance and Payroll Software", "Software", "Directorate of Technical Education", "Ministry of Education", "Haryana", 490_000, 0, 15, "1 Project"),
        ("Supply of Biometric Devices and Software", "Hardware", "District e-Governance Society", "Ministry of Electronics and IT", "Odisha", 350_000, 7_000, 6, "50 Nos", "Product"),

        # --- Other tenders that should match ----------------------------------
        ("Social Media Management for State Tourism Campaign", "Social Media Management", "Department of Tourism", "Ministry of Tourism", "Goa", 250_000, 5_000, 13, "1 Year"),
        ("Digital Marketing and Lead Generation Services", "Digital Marketing", "Small Industries Development Bank", "Ministry of Finance", "Delhi", 400_000, 8_000, 16, "1 Project"),
        ("Production of Promotional Videos", "Video Production", "Department of Agriculture", "Ministry of Agriculture", "Punjab", 300_000, 6_000, 11, "4 Videos"),
        ("Design and Printing of Brochures and Booklets", "Printing", "Department of Culture", "Ministry of Culture", "Bihar", 200_000, 4_000, 9, "5,000 Nos", "Product"),
        ("Content Writing for Annual Reports", "Content Writing", "Central Board of Direct Taxes", "Ministry of Finance", "Delhi", 80_000, 0, 14, "1 Project"),
        ("Graphic Design Services for Awareness Campaign", "Graphic Design", "National Health Mission", "Ministry of Health and Family Welfare", "Chhattisgarh", 150_000, 0, 10, "1 Project"),
        ("Event Management for Annual Conference", "Event Management", "Confederation of Indian Industry", "Ministry of Commerce and Industry", "Telangana", 450_000, 9_000, 7, "1 Event"),
        ("Photography and Videography for Official Events", "Photography", "Press Information Bureau", "Ministry of Information and Broadcasting", "Delhi", 100_000, 2_000, 12, "1 Year"),
        ("Branding and Creative Design for New Scheme", "Branding", "Ministry of Skill Development", "Ministry of Skill Development", "Delhi", 420_000, 8_400, 17, "1 Project"),

        # --- Should be filtered out -------------------------------------------
        ("Construction of Office Building at District HQ", "Civil Works", "Public Works Department", "Ministry of Housing and Urban Affairs", "Rajasthan", 2_000_000, 40_000, 20, "1 Work"),
        ("Furniture Supply for Government Schools", "Furniture", "Samagra Shiksha Abhiyan", "Ministry of Education", "Uttar Pradesh", 500_000, 10_000, 15, "1 Lot", "Product"),
        ("Hiring of Security Guards for Office Campus", "Manpower Services", "Central Public Works Department", "Ministry of Housing and Urban Affairs", "Delhi", 1_500_000, 30_000, 18, "1 Year"),
        ("Vehicle Hire Services for Field Officers", "Vehicle Hiring", "Department of Rural Development", "Ministry of Rural Development", "Jharkhand", 800_000, 16_000, 12, "1 Year"),
        ("Housekeeping and Gardening Services", "Housekeeping", "District Court", "Ministry of Law and Justice", "Madhya Pradesh", 700_000, 14_000, 11, "1 Year"),

        # --- Edge cases --------------------------------------------------------
        ("Enterprise Software with High Turnover Requirement", "Software", "Large Public Sector Undertaking", "Ministry of Heavy Industries", "Maharashtra", 3_000_000, 60_000, 20, "1 Project"),
        ("Website Development - Urgent Requirement", "Website Development", "State Election Commission", "Ministry of Law and Justice", "Uttar Pradesh", 750_000, 15_000, 3, "1 Project"),
        ("Software Support with High EMD", "Software", "Metro Rail Corporation", "Ministry of Housing and Urban Affairs", "Delhi", 1_800_000, 120_000, 22, "1 Year"),
        ("Cloud Storage Subscription", "Cloud", "National Archives of India", "Ministry of Culture", "Delhi", 490_000, 9_800, 19, "1 Year"),
        ("Civil and Electrical Works for Data Centre", "Civil Works", "National Informatics Centre", "Ministry of Electronics and IT", "Delhi", 2_100_000, 42_000, 25, "1 Work"),
    ]
    return [_row(index + 1, *row) for index, row in enumerate(rows)]
