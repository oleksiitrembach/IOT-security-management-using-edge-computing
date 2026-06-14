FROM python:3.12-slim
# iproute2 dostarcza `tc` do emulacji opoznienia sieciowego (netem) w kontenerze central
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY detector.py device_sim.py edge_node.py central.py ./
CMD ["python", "edge_node.py"]
