#!/usr/bin/env python3
"""
S3 Pipeline Runner

Polls the internal API for content items pending processing,
downloads originals from S3_ORIG_BUCKET, encodes them (H264 for
video, WebP for image sets), uploads results to S3_BUCKET, and
marks each item as ready via the API.
"""

from s3_pipeline.runner import run


if __name__ == "__main__":
    run()
