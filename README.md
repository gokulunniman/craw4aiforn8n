# craw4aiforn8n# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate


# Install the package
pip install crawl4ai

# Run setup command
crawl4ai-setup

# Run diagnostics
crawl4ai-doctor


To integrate the new news crawler with your existing HTTP endpoint, we need to modify your API file to support both crawlers or create a new endpoint. Let me help you with both approaches.
Enhanced API with News Crawler SupportClick to open code
Now, to use the new news crawler in your n8n HTTP node, you just need to modify your JSON body to include the crawler_type parameter. Here's how your JSON body should look:
jsonCopy{
  "urls": [
    "https://www.hindustantimes.com/topic/study-abroad/news",
    "https://wenr.wes.org/"
  ],
  "max_pages": 100,
  "exclude_external_links": true,
  "exclude_social_media_links": true,
  "exclude_domains": [],
  "output_dir": "crawled_docs",
  "crawler_type": "news",
  "max_depth": 3
}
The changes are:

Added "crawler_type": "news" to use the new news crawler
Added "max_depth": 3 to control how deep the crawler goes into the website

You can:

Use "crawler_type": "news" for the new news crawler
Use "crawler_type": "standard" or omit it for the original crawler

The API will automatically:

Detect which crawler to use based on the crawler_type
Apply the appropriate settings
Return results in the same format for compatibility

Your existing n8n workflows will continue to work, and you can switch between crawlers just by changing the crawler_type parameter in your HTTP request.
To deploy this:

Update your api.py file with this new code
Push the changes to GitHub
Railway will automatically deploy the updates
Update your n8n HTTP node's JSON body to include the new parameters

Would you like me to explain any part of this in more detail or help you with testing the new setup?
