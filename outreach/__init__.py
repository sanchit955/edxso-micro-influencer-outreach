"""Automated Micro-Influencer Outreach System (EDXSO Assignment 1).

Pipeline stages, each in its own module:
  discovery       -> collect candidate YouTube channels for a niche
  enrichment      -> fetch each channel page and parse real public data
  filtering       -> apply the niche filter, every record gets Pass/Fail + reason
  personalization -> dynamic per-influencer email pitch + Instagram DM
  sending         -> simulated sending layer with duplicate protection
"""

__version__ = "1.0.0"
