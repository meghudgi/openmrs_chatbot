import ollama
from utils.logger import setup_logger
from utils.config import OLLAMA_HOST, OLLAMA_MODEL
import json
import time
from datetime import datetime

logger = setup_logger(__name__)

# Configure Ollama client with connection retry
class OllamaClientWrapper:
    def __init__(self, host=OLLAMA_HOST):
        self.host = host
        self.client = None
        self.connect()
    
    def connect(self):
        """Connect to Ollama with retries"""
        try:
            self.client = ollama.Client(host=self.host)
            return True
        except Exception as e:
            logger.warning(f"Ollama connection failed: {e}")
            return False
    
    def generate(self, *args, **kwargs):
        """Generate with Ollama, return None if unavailable"""
        try:
            if not self.client:
                self.connect()
            
            result = self.client.generate(*args, **kwargs)
            return result
        except (KeyboardInterrupt, TimeoutError):
            logger.warning("Ollama request timed out or interrupted")
            return None
        except Exception as e:
            logger.warning(f"Ollama generation failed: {e}")
            return None

ollama_client = OllamaClientWrapper(host=OLLAMA_HOST)


class ResponseAgent:
    def __init__(self):
        self.model = OLLAMA_MODEL
        self.client = ollama_client
    
    def calculate_age_from_birthdate(self, birthdate_str):
        """Calculate patient age in years from birthdate string or date object (YYYY-MM-DD)"""
        try:
            if not birthdate_str or birthdate_str == 'N/A':
                return None
            
            # Handle date objects directly
            if hasattr(birthdate_str, 'year'):  # It's a date or datetime object
                birthdate = birthdate_str
                today = datetime.now().date()
                if hasattr(today, 'year'):  # Make sure today is a date object
                    age = today.year - birthdate.year
                    if (today.month, today.day) < (birthdate.month, birthdate.day):
                        age -= 1
                    return age
            
            # Handle string format
            birthdate = datetime.strptime(str(birthdate_str).split()[0], '%Y-%m-%d')
            today = datetime.now()
            age = today.year - birthdate.year
            
            # Adjust if birthday hasn't occurred this year
            if (today.month, today.day) < (birthdate.month, birthdate.day):
                age -= 1
            
            return age
        except Exception as e:
            logger.warning(f"Failed to calculate age from {birthdate_str}: {e}")
            return None

    def generate_medication_response_with_context(self, question, context_data):
        """Generate medication dose response with patient clinical context for doctors"""
        mcp_data = context_data.get("mcp_data", {})
        med_results = mcp_data.get("medications", {})
        patient_data = context_data.get("patient_data", {})
        sources = context_data.get("sources", [])
        
        response_parts = []
        response_parts.append("Answer:")
        
        # Extract relevant patient information
        patient_weight_kg = None
        patient_age = None
        
        if patient_data.get("vitals") and patient_data["vitals"].get("data"):
            for vital in patient_data["vitals"]["data"]:
                vital_name = vital.get('vital_name', '').lower()
                if 'weight' in vital_name and 'kg' in vital_name.lower():
                    patient_weight_kg = vital.get('value_numeric')
                    if patient_weight_kg:
                        response_parts.append(f"\nPATIENT WEIGHT: {patient_weight_kg} kg")
                        break
        
        if patient_data.get("patient") and patient_data["patient"].get("data"):
            p = patient_data["patient"]["data"][0]
            birthdate = p.get('birthdate')
            if birthdate:
                patient_age = self.calculate_age_from_birthdate(birthdate)
                if patient_age:
                    response_parts.append(f"PATIENT AGE: {patient_age} years")
        
        # Medication and dose information
        if med_results.get("dose_calculation"):
            dose_info = med_results["dose_calculation"]
            response_parts.append(f"\nRECOMMENDED DOSE:")
            if isinstance(dose_info, dict):
                for key, value in dose_info.items():
                    response_parts.append(f"  - {key}: {value}")
            else:
                response_parts.append(f"  - {dose_info}")
        
        # Medication details
        if med_results.get("results") and len(med_results["results"]) > 0:
            med_info = med_results["results"][0]
            med_name = med_info.get("name", "Medication")
            response_parts.append(f"\nMEDICATION: {med_name}")
            
            if med_info.get("description"):
                response_parts.append(f"DESCRIPTION: {med_info.get('description')}")
            if med_info.get("common_indications"):
                response_parts.append(f"INDICATIONS: {med_info.get('common_indications')}")
        
        # Patient clinical context for decision-making
        clinical_context = self.extract_clinical_context(patient_data)
        if clinical_context:
            response_parts.append(f"\nCLINICAL CONTEXT:")
            response_parts.append(clinical_context)
        
        # Warnings/considerations
        response_parts.append("\nCONSIDERATIONS:")
        response_parts.append("- Always verify dose against current clinical guidelines")
        response_parts.append("- Check for patient allergies and contraindications")
        response_parts.append("- Monitor for adverse effects")
        
        response_parts.append("\nConfidence: HIGH")
        
        return "\n".join(response_parts)

    def extract_clinical_context(self, patient_data):
        """Extract relevant clinical context for medication decisions
        Used when doctor asks for dose - shows conditions, recent symptoms, vitals
        """
        if not patient_data:
            return ""
        
        context = []
        
        # Recent vital signs
        if patient_data.get("vitals") and patient_data["vitals"].get("data"):
            context.append("RECENT VITALS:")
            for vital in patient_data["vitals"]["data"][:3]:
                vital_name = vital.get('vital_name', 'Unknown')
                value = vital.get('value_numeric', vital.get('value_text', 'N/A'))
                context.append(f"  - {vital_name}: {value}")
        
        # Recent conditions/diagnoses
        if patient_data.get("conditions") and patient_data["conditions"].get("data"):
            conditions = patient_data["conditions"]["data"][:5]
            if conditions:
                context.append("\nCURRENT CONDITIONS:")
                for cond in conditions:
                    cond_name = cond.get('condition_name', 'Unknown')
                    context.append(f"  - {cond_name}")
        
        # Recent observations (symptoms/findings)
        if patient_data.get("observations") and patient_data["observations"].get("data"):
            obs_list = patient_data["observations"]["data"][:3]
            if obs_list:
                context.append("\nRECENT OBSERVATIONS:")
                for obs in obs_list:
                    concept = obs.get('concept_name', 'Unknown')
                    value = obs.get('value_numeric', obs.get('value_text', 'N/A'))
                    context.append(f"  - {concept}: {value}")
        
        return "\n".join(context)

    def format_patient_data_for_llm(self, patient_data):
        """Format structured patient data into readable text for LLM"""
        if not patient_data:
            return "No patient data available."
        
        formatted = []
        calculated_age = None
        
        # Patient demographics
        if patient_data.get("patient") and patient_data["patient"].get("data"):
            p = patient_data["patient"]["data"][0]
            formatted.append("PATIENT DEMOGRAPHICS:")
            
            # Patient Identifier (the actual ID like 1000001W)
            patient_id = p.get('patient_identifier', p.get('patient_id', 'N/A'))
            formatted.append(f"  - Patient ID: {patient_id}")
            
            # Patient Name
            given_name = p.get('given_name', 'N/A')
            family_name = p.get('family_name', 'N/A')
            full_name = f"{given_name} {family_name}".strip()
            if full_name and full_name != "N/A N/A":
                formatted.append(f"  - Name: {full_name}")
            
            formatted.append(f"  - Gender: {p.get('gender', 'N/A')}")
            
            birthdate = p.get('birthdate', 'N/A')
            # Ensure birthdate is properly formatted to avoid LLM misinterpretation
            if birthdate != 'N/A':
                # Convert datetime.date to string in YYYY-MM-DD format
                if hasattr(birthdate, 'strftime'):
                    birthdate = birthdate.strftime('%Y-%m-%d')
                else:
                    birthdate = str(birthdate)
            formatted.append(f"  - Birth Date: {birthdate}")
            
            # Calculate and include age
            calculated_age = self.calculate_age_from_birthdate(birthdate)
            if calculated_age is not None:
                formatted.append(f"  - Current Age: {calculated_age} years")
            
            formatted.append(f"  - Address: {p.get('address1', 'N/A')}, {p.get('city_village', 'N/A')}")
            formatted.append("")
        
        # Vital signs (most recent)
        if patient_data.get("vitals") and patient_data["vitals"].get("data"):
            vitals_list = patient_data["vitals"]["data"]
            if vitals_list:
                formatted.append("VITAL SIGNS (Most Recent):")
                for vital in vitals_list:
                    vital_name = vital.get('vital_name', 'Unknown')
                    value_numeric = vital.get('value_numeric')
                    value_text = vital.get('value_text')
                    date = vital.get('obs_datetime', 'N/A')
                    
                    if value_numeric is not None:
                        formatted.append(f"  - {vital_name}: {value_numeric} ({date})")
                    elif value_text:
                        formatted.append(f"  - {vital_name}: {value_text} ({date})")
                formatted.append("")
        
        # Recent observations
        if patient_data.get("observations") and patient_data["observations"].get("data"):
            obs_list = patient_data["observations"]["data"][:5]
            if obs_list:
                formatted.append("RECENT OBSERVATIONS (last 5):")
                for obs in obs_list:
                    concept = obs.get('concept_name', 'Unknown')
                    value = obs.get('value_numeric') or obs.get('value_text', 'N/A')
                    date = obs.get('obs_datetime', 'N/A')
                    formatted.append(f"  - {concept}: {value} ({date})")
                formatted.append("")
        
        # Encounters
        if patient_data.get("encounters") and patient_data["encounters"].get("data"):
            enc_list = patient_data["encounters"]["data"][:3]
            if enc_list:
                formatted.append("RECENT ENCOUNTERS (last 3):")
                for enc in enc_list:
                    enc_type = enc.get('encounter_type_name', 'Unknown')
                    date = enc.get('encounter_datetime', 'N/A')
                    formatted.append(f"  - {enc_type} on {date}")
                formatted.append("")
        
        # Conditions
        if patient_data.get("conditions") and patient_data["conditions"].get("data"):
            cond_list = patient_data["conditions"]["data"]
            if cond_list:
                formatted.append("PATIENT CONDITIONS:")
                for cond in cond_list:
                    name = cond.get('condition_name', 'Unknown')
                    onset = cond.get('onset_date', 'N/A')
                    formatted.append(f"  - {name} (onset: {onset})")
        
        return "\n".join(formatted)
        
        return "\n".join(formatted)

    def _clean_response(self, response_text):
        """Clean response by aggressively removing hallucinated content"""
        if not response_text:
            return ""
        
        text = response_text.strip()
        
        # AGGRESSIVE MARKERS for non-medical content
        non_medical_markers = [
            "\nRules of the Puzzle",
            "\nRules:",
            "\nThe goal of",
            "\nHere are some hints",
            "\nThis logic-based puzzle",
            "Consider ",
            "\nConsider",
            "\nUse ",
            "\nUsing ",
            "\nThink",
            "\nAssuming",
            "To calculate",
            "to calculate",
            "subtract their",
            "subtract the",
            "This will give",
            "Therefore, the",
            "Using this calculation",
            "By calculating",
        ]
        
        for marker in non_medical_markers:
            if marker in text:
                idx = text.find(marker)
                if idx > 0:
                    text = text[:idx].strip()
                    break
        
        # Remove lines with gaming/puzzle language
        lines = text.split('\n')
        cleaned_lines = []
        skip_rest = False
        
        for line in lines:
            line_lower = line.lower()
            
            # Stop processing at puzzle/game content
            if any(skip in line_lower for skip in [
                'rules of the puzzle',
                'the goal of',
                'here are some hints',
                'logic-based puzzle',
                'patient alice',
                'patient bob',
                'patient charlie',
                'inspired by',
                'the game is'
            ]):
                skip_rest = True
                continue
            
            # Skip numbered puzzle hints
            if skip_rest or any(f'{i}. ' in line_lower for i in range(1, 7)):
                if line.strip() and not line_lower.startswith('when to see'):
                    continue
            
            # Skip lines that are clearly non-medical
            if any(x in line_lower for x in [
                'Consider',
                'suppose',
                'imagine',
                'hypothetical'
            ]):
                continue
                
            cleaned_lines.append(line)
        
        result = '\n'.join(cleaned_lines).strip()
        
        # Clean up multiple newlines
        while '\n\n\n' in result:
            result = result.replace('\n\n\n', '\n\n')
        
        return result

    def generate_doctor_response(self, question, context_data):
        """Generate response for doctor queries with STRICT hallucination prevention"""
        sources = context_data.get("sources", [])
        kb_content = context_data.get("kb_content", "")
        patient_data_raw = context_data.get("patient_data", {})
        
        # Format patient data properly
        patient_data_formatted = self.format_patient_data_for_llm(patient_data_raw)
        
        # Check if we actually have patient data
        has_patient_data = patient_data_formatted and len(patient_data_formatted) > 10
        
        # Limit content to most recent for speed - more generous for doctors
        if len(patient_data_formatted) > 1500:
            patient_data_formatted = patient_data_formatted[:1500] + "\n[... data truncated ...]"
        if len(kb_content) > 500:
            kb_content = kb_content[:500] + "\n[... knowledge base truncated ...]"

        # Build prompt with explicit instructions
        data_status = "PATIENT DATA AVAILABLE" if has_patient_data else "NO PATIENT DATA IN SYSTEM"
        
        prompt = f"""You are a clinical decision support system. You MUST ONLY report ACTUAL FACTS from the provided medical record.

INSTRUCTION LEVEL CRITICAL:
- ONLY use information that appears in the provided patient data section
- If information is NOT in the data, you MUST explicitly say "This information is not available in the patient record"
- Do NOT infer, calculate, guess, or assume values NOT in the data
- Do NOT provide examples or hypothetical scenarios
- Do NOT make up patient demographics like ages, names, or vital signs

DATA AVAILABILITY STATUS: {data_status}

Doctor's Question: {question}

VERIFIED PATIENT MEDICAL DATA:
{patient_data_formatted if has_patient_data else "NO PATIENT DATA AVAILABLE IN SYSTEM"}

MEDICAL KNOWLEDGE REFERENCE:
{kb_content if kb_content else "General information only"}

RESPONSE REQUIREMENTS:
1. Answer ONLY using the provided verified data above
2. If data is not available, clearly state "This information is not available in the patient record"
3. Do NOT invent or simulate patient information
4. Report exactly what is shown in the data section

Your response:"""

        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                stream=False,
            )
            if response and response.get('response'):
                logger.info("Response generated for doctor")
                cleaned = self._clean_response(response['response'])
                if not cleaned:
                    cleaned = response['response'].strip()
                return f"Answer:\n{cleaned}\n\nConfidence: MEDIUM"
            else:
                logger.warning("Ollama returned empty response")
                return self._get_fallback_response("doctor", patient_data_raw, sources)
        except Exception as e:
            logger.error(f"Response generation failed: {str(e)}")
            return self._get_fallback_response("doctor", patient_data_raw, sources)

    def generate_patient_response(self, question, context_data):
        """Generate response for patient queries - patient viewing their OWN medical data"""
        kb_content = context_data.get("kb_content", "")
        patient_data_raw = context_data.get("patient_data", {})
        sources = context_data.get("sources", [])
        
        # Format patient data if available (patients have full access to their own data)
        patient_data_formatted = self.format_patient_data_for_llm(patient_data_raw) if patient_data_raw else ""
        
        # Limit content for faster inference with smaller model
        if len(kb_content) > 400:
            kb_content = kb_content[:400] + "\n[... content truncated ...]"
        if len(patient_data_formatted) > 600:
            patient_data_formatted = patient_data_formatted[:600] + "\n[... data truncated ...]"

        # Build prompt with patient data - EMPHASIZE this is the patient's own data
    def generate_patient_response(self, question, context_data):
        """Generate response for patient queries - STRICT HALLUCINATION PREVENTION"""
        kb_content = context_data.get("kb_content", "")
        patient_data_raw = context_data.get("patient_data", {})
        sources = context_data.get("sources", [])
        
        # Format patient data if available (patients have full access to their own data)
        patient_data_formatted = self.format_patient_data_for_llm(patient_data_raw) if patient_data_raw else ""
        has_patient_data = patient_data_formatted and len(patient_data_formatted) > 10
        
        # Limit content for faster inference with smaller model
        if len(kb_content) > 400:
            kb_content = kb_content[:400] + "\n[... content truncated ...]"
        if len(patient_data_formatted) > 600:
            patient_data_formatted = patient_data_formatted[:600] + "\n[... data truncated ...]"

        # Build prompt with patient data - EMPHASIZE this is the patient's own data
        data_status = "PATIENT DATA AVAILABLE" if has_patient_data else "NO PATIENT DATA IN SYSTEM"
        
        prompt = f"""You are a patient health assistant explaining medical information to patients.

INSTRUCTION LEVEL CRITICAL - YOU MUST FOLLOW THESE RULES:
1. ONLY use information that appears in the provided medical record
2. If information is NOT in the record, you MUST say "This information is not in your medical record"
3. Do NOT infer, calculate, guess, or assume values NOT in the record
4. Do NOT create patient scenarios, examples, or what-if scenarios
5. Do NOT make up health information to "be helpful"
6. NEVER provide specific health values (age, weight, BP, etc.) unless they're in the record

DATA STATUS: {data_status}

Patient's Question: {question}

YOUR MEDICAL RECORD:
{patient_data_formatted if has_patient_data else "NO MEDICAL RECORD DATA IN THE SYSTEM - Please contact your clinic to register."}

GENERAL HEALTH INFORMATION:
{kb_content if kb_content else "General wellness information"}

YOUR RESPONSE MUST:
1. Use ONLY information from your medical record shown above
2. Never invent or simulate personal health information
3. Clearly state when information is not available in your record
4. Direct patients to contact their healthcare provider for missing information

Your response:"""

        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                stream=False,
            )
            if response and response.get('response'):
                logger.info("Response generated for patient")
                resp_text = response['response'].strip()
                cleaned = self._clean_response(resp_text)
                if not cleaned:
                    cleaned = resp_text
                return f"Answer:\n{cleaned}\n\nWhen to See Doctor:\nConsult a healthcare provider if symptoms persist or for any health concerns.\n\nConfidence: MEDIUM"
            else:
                logger.warning("Ollama returned empty response")
                return self._get_fallback_response("patient", patient_data_raw, sources)
        except Exception as e:
            logger.error(f"Response generation failed: {str(e)}")
            return self._get_fallback_response("patient", patient_data_raw, sources)

    def _get_fallback_response(self, user_type, patient_data=None, sources=None):
        """Generate appropriate fallback response based on available data"""
        if user_type.upper() == "DOCTOR":
            # For doctors, provide structured response with what we have
            response_parts = []
            response_parts.append("Answer:")
            
            if patient_data and (patient_data.get("observations") and patient_data["observations"].get("data")):
                obs_count = len(patient_data["observations"].get("data", []))
                response_parts.append(f"Found {obs_count} recent observations for this patient.")
            elif patient_data and (patient_data.get("encounters") and patient_data["encounters"].get("data")):
                enc_count = len(patient_data["encounters"].get("data", []))
                response_parts.append(f"Found {enc_count} recent encounters for this patient.")
            else:
                response_parts.append("Unable to generate a full clinical response at this time.")
            
            response_parts.append("\nData Sources:")
            if sources:
                for source in sources:
                    response_parts.append(f"  - {source}")
            else:
                response_parts.append("  - Limited data available")
            
            response_parts.append("\nConfidence: LOW")
            response_parts.append("\nNote: For complete clinical decision support, please review the patient EHR directly.")
            return "\n".join(response_parts)
        else:
            # For patients, simple guidance
            return """Answer:
I don't have enough verified information to answer your question fully.

Home Care:
For immediate health concerns, follow any guidance from your healthcare provider.

When to See Doctor:
Contact your healthcare provider if:
- Your symptoms worsen
- You develop new or unusual symptoms  
- You have questions about your health

Confidence: LOW

Note: Always consult a healthcare professional for medical advice."""

    def validate_response_safety(self, response, user_type):
        """Check if response contains appropriate confidence markers"""
        if not response:
            return False
        
        response_lower = response.lower()
        # For doctors, should have some data reference
        if user_type.upper() == "DOCTOR":
            has_data = any(word in response_lower for word in ['observation', 'encounter', 'data', 'analysis'])
            return has_data or 'insufficient' in response_lower
        
        # For patients, should have safety guidance
        return 'healthcare' in response_lower or 'doctor' in response_lower or 'provider' in response_lower

    def generate_milestone_response(self, question, context_data, user_type="DOCTOR"):
        """Generate response for milestone queries with patient age context"""
        milestone_data = context_data.get("mcp_data", {}).get("milestones", {})
        patient_age = milestone_data.get("patient_age")
        milestone_results = milestone_data.get("results", [])
        patient_data = context_data.get("patient_data", {})
        
        # Format milestone data for display
        milestone_text = ""
        if milestone_results:
            for milestone_group in milestone_results:
                age_months = milestone_group.get("age_months", 0)
                mtype = milestone_group.get("type", "Unknown")
                milestones_list = milestone_group.get("milestones", [])
                
                milestone_text += f"\n{mtype} Milestones (Age {age_months} months):\n"
                for m in milestones_list:
                    milestone_text += f"  • {m}\n"
        
        # Get patient name if available
        patient_name = "the patient"
        if patient_data.get("patient") and patient_data["patient"].get("data"):
            p = patient_data["patient"]["data"][0]
            given_name = p.get('given_name', '')
            family_name = p.get('family_name', '')
            full_name = f"{given_name} {family_name}".strip()
            if full_name:
                patient_name = full_name
        
        # Build response with patient context for doctors, patient-friendly for patients
        # Case-insensitive comparison for user_type
        if user_type and user_type.upper() == "DOCTOR":
            response_text = f"""PATIENT: {patient_name}
AGE: {patient_age} years ({patient_age * 12} months)

DEVELOPMENTAL MILESTONES:
{milestone_text if milestone_text else "Limited milestone data available for this age group."}

CLINICAL ASSESSMENT:
Based on the patient's age ({patient_age} years), the milestones listed above are typical developmental expectations. Monitor for any significant delays or concerns in these areas during clinical assessment.
"""
        else:
            response_text = f"""Hello {patient_name},

Here are the developmental milestones you should be working towards at {patient_age} years old:
{milestone_text if milestone_text else "Limited milestone data available for this age group."}

TIPS FOR HEALTHY DEVELOPMENT:
• Engage in regular play and social interaction
• Encourage learning through age-appropriate activities
• Maintain regular check-ups with your healthcare provider
• Report any concerns about development to your doctor

If you have concerns about your child's development, please consult with your healthcare provider.
"""
        
        return response_text

