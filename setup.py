from setuptools import setup

setup(
    name="watchpdf",
    version="0.1",
    py_modules=["WatchPDFFile"],
    install_requires=[
        "watchfiles",
        "pdf2image",
        "requests",
        "google-cloud-vision",
        "ollama"
    ],
    entry_points={
        'console_scripts': [
            'run-watcher=WatchPDFFile:main'
        ]
    }
)