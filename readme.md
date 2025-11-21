
---

# 🔌 **Pathway Connectors (Short Description)**

Pathway uses **connectors** to move data **in and out** of your application.

### **Input Connectors (Data In)**

Input connectors are used to **bring external data into Pathway**.
They can read data from various sources like:

* Files (CSV, JSON, Parquet)
* Databases
* Streams (Kafka, Pub/Sub)
* APIs or webhooks
* Demo generators (for testing)

These connectors turn raw data into **Pathway tables** so the system can process it.

---

### **Output Connectors (Data Out)**

Output connectors are used to **send processed data from Pathway to the outside world**.
They can write to:

* Files (CSV, JSON)
* Databases
* Streams (Kafka)
* REST APIs
* The terminal (print)

These allow Pathway to deliver results back to your application or other systems.

---

### **In simple words**

**Input connectors pull data into Pathway.
Output connectors push data out of Pathway.**

They make it easy to connect Pathway with real-world data sources and destinations.

---

# Steps to Run docker container 
```bash
Run docker container in interactive mode 
```
```bash
docker run -it --rm -v "C:\majorprojects\pullSharkLLM:/app" pathwaycom/pathway:latest bash
```

```bash
cd /app
python3 api/test.py
```

# Running a template 
```bash 
cd llm-app
```
```bash
cd templates/multimodal_rag
```
```bash
docker compose down
docker compose up --build
```