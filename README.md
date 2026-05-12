# Clinical AI Assistant for OpenMRS

A modular clinical chatbot system designed to support natural language clinical query answering within the OpenMRS ecosystem. The project combines structured Electronic Health Record (EHR) retrieval with domain-specific clinical knowledge pipelines to provide safe, explainable, and context-aware responses for both healthcare providers and patients.

## Overview

Healthcare systems often require clinicians to manually navigate multiple interfaces and records to retrieve patient information, review immunization status, verify allergies, or calculate medication doses. This project aims to simplify those workflows through a conversational interface integrated with OpenMRS.

The system supports:

* OpenMRS patient data retrieval
* Allergy checking
* Immunization tracking
* Pediatric milestone guidance
* Weight-based drug dosing assistance
* Role-based response generation for doctors and patients

The architecture focuses on reducing hallucinations and improving reliability through a hybrid intent-classification pipeline and controlled retrieval mechanisms.

---

# Key Features

## OpenMRS Integration

* Retrieves patient information from OpenMRS
* Structured database querying using NLP-to-SQL workflow
* PostgreSQL backend integration

## Dual Response Pipelines

### Doctor Pipeline

* Detailed clinical responses
* Expanded medical context
* Structured clinical information access

### Patient Pipeline

* Simplified and safer explanations
* Limited clinical complexity
* Patient-friendly guidance

## Clinical Modules

* Allergy checking
* Immunization schedule support
* Pediatric milestone guidance
* Drug dosage assistance
* Patient history retrieval

---

# System Architecture

## Hybrid Intent Classification

The project uses a two-layer intent classification pipeline to balance precision and semantic flexibility.

### Layer 1 - Keyword-Based Routing

A deterministic keyword-based classifier handles high-priority clinical intents such as:

* allergies
* immunizations
* milestones
* dosing
* patient lookup

This layer provides:

* high precision
* explainability
* controlled routing for critical workflows

### Layer 2 - Semantic Similarity Matching

If confidence from Layer 1 is insufficient, the query is passed to a semantic embedding layer using sentence embeddings (MiniLM-based embeddings).

This layer:

* handles paraphrased queries
* improves semantic understanding
* reduces dependency on exact keywords

Confidence thresholds are used to determine routing behavior.

---

# Knowledge Sources

The system combines:

* Structured EHR data from OpenMRS
* Clinical JSON knowledge bases
* Retrieval-Augmented Generation (RAG) workflows
* ChromaDB vector storage

Knowledge bases currently include:

* medications
* immunization schedules
* pediatric milestones

---

# Technologies Used

## Backend

* Python
* PostgreSQL
* OpenMRS API

## NLP / AI

* Sentence Transformers (MiniLM embeddings)
* ChromaDB
* Retrieval-Augmented Generation (RAG)

## Data Handling

* JSON
* SQL
* NLP-to-SQL querying

---

# Design Considerations

This project prioritizes:

* clinical safety
* explainability
* controlled information retrieval
* reduced hallucination risk

Instead of relying fully on generative LLM behavior, the system uses hybrid routing and constrained retrieval methods for safer responses in healthcare settings.

---

# Current Limitations

* Keyword routing requires controlled maintenance for critical intents
* The project currently uses limited proof-of-concept knowledge bases
* Open-source LLM hallucination remains a challenge in unrestricted clinical response generation
* Clinical recommendations are not intended to replace professional medical judgment

---

# Future Enhancements

Planned improvements include:

* enhanced supervisory/validation layers
* improved semantic intent classification
* MedAgentBench-based evaluation
* progressive disclosure mechanisms
* expanded clinical knowledge bases
* improved clinical response evaluation pipelines

---

# Research Motivation

The project explores how conversational AI can improve usability and accessibility in clinical systems while maintaining safety, transparency, and controlled decision support in healthcare environments.



This project is intended for academic and research purposes only. It is not designed for direct clinical deployment or autonomous medical decision-making.
