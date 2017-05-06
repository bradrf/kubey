FROM python:2.7.13

RUN curl -LO https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl && mv /kubectl /usr/bin/kubectl && chmod +x /usr/bin/kubectl

RUN pip install kubey

ENTRYPOINT ["kubey"]
