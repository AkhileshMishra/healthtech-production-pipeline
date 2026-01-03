import os

def lambda_handler(event, context):
    # Serve a static HTML file packaged with the lambda
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "index.html"), "r", encoding="utf-8") as f:
        html = f.read()

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store",
        },
        "body": html,
    }
