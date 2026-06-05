# Extraction and Summarization

Provider metadata is often too thin for research. Searchbox attempts to extract useful text from result URLs.

## HTML

HTML extraction tries to keep article text and discard navigation, cookie banners, and boilerplate.

## PDF

PDF extraction downloads within size limits and extracts text. It can fail on scanned PDFs, blocked downloads, oversized files, or publisher interstitials.

## Long Text

When text exceeds the summary threshold, Searchbox should send the full allowed source text to the summarizer and place the summary in `content`.

## Raw Content

Fuller extracted text can be preserved in `raw_content`, especially for science responses.

## Failure

If extraction fails, Searchbox should keep useful metadata and mark the failure with quality flags.
