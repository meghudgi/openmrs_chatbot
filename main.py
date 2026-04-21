import json
import os
from datetime import datetime
from agents.triage_agent import TriageAgent
from agents.sql_agent import SQLAgent
from agents.mcp_agent import MCPAgent
from agents.knowledge_agent import KnowledgeAgent
from agents.response_agent import ResponseAgent
from agents.validation_agent import ValidationAgent
from utils.logger import setup_logger
from utils.config import RESPONSES_FILE

logger = setup_logger(__name__)


class ClinicalChatbot:
    
    def __init__(self):
        logger.info("Initializing Clinical Chatbot...")
        self.triage_agent = TriageAgent()
        self.sql_agent = SQLAgent()
        self.mcp_agent = MCPAgent()
        self.knowledge_agent = KnowledgeAgent()
        self.response_agent = ResponseAgent()
        self.validation_agent = ValidationAgent()
        self.user_role = None  # Track user role for testing: 'doctor' or 'patient'
        logger.info("Chatbot initialized")
    
    def select_user_role(self):
        """Prompt user to select their role (doctor or patient) for testing"""
        print("\n" + "="*60)
        print("CLINICAL CHATBOT - USER ROLE SELECTION")
        print("="*60)
        print("Please select your role:")
        print("  1. Doctor")
        print("  2. Patient")
        print("="*60)
        
        while True:
            choice = input("\nEnter your choice (1 or 2): ").strip()
            if choice == "1":
                self.user_role = "doctor"
                logger.info("User role selected: DOCTOR")
                print("\nYou are logged in as: DOCTOR")
                return
            elif choice == "2":
                self.user_role = "patient"
                logger.info("User role selected: PATIENT")
                print("\nYou are logged in as: PATIENT")
                return
            else:
                print("[ERROR] Invalid choice. Please enter 1 or 2.")
    
    def format_full_name(self, patient):
        """Format patient full name from given_name and family_name"""
        given = patient.get('given_name', 'N/A')
        family = patient.get('family_name', 'N/A')
        if given != 'N/A' and family != 'N/A':
            return f"{given} {family}"
        elif given != 'N/A':
            return given
        elif family != 'N/A':
            return family
        return 'N/A'
    
    def format_response(self, response_dict):
        """Format response dictionary into readable text"""
        if isinstance(response_dict, dict):
            parts = []
            if response_dict.get("answer"):
                parts.append(f"Answer:\n{response_dict['answer']}")
            if response_dict.get("when_to_see_doctor"):
                parts.append(f"\nWhen to See Doctor:\n{response_dict['when_to_see_doctor']}")
            if response_dict.get("confidence"):
                confidence = response_dict['confidence']
                parts.append(f"\nConfidence: {confidence}")
            return "\n".join(parts)
        return str(response_dict)

    def process_query(self, user_question, selected_patient_id=None):
        """Process user query with optional selected patient context"""
        logger.info(f"Query received: {user_question}")
        
        triage_result = self.triage_agent.triage(user_question)
        # Use user's selected role if available, otherwise use triage classification
        user_type = self.user_role if self.user_role else triage_result["user_type"]
        intent = triage_result["intent"]
        # CRITICAL FIX: Use selected_patient_id from context, fallback to extracted ID
        patient_id = selected_patient_id or triage_result["patient_id"]

        context_data = {
            "sources": [],
            "kb_content": "",
            "patient_data": None,
            "mcp_data": {},
            "db_error": None  # Track database errors
        }

        # Query patient record if PATIENT_RECORD_QUERY intent
        if intent == "PATIENT_RECORD_QUERY" and patient_id:
            # First validate that the patient ID exists
            validation_status, patient_info, validation_error = self.triage_agent.validate_patient_id(patient_id)
            
            if validation_status is None:
                # Database connection error
                context_data["db_error"] = validation_error
                context_data["sources"] = []
                logger.warning(f"Cannot validate patient ID due to database error: {validation_error}")
            elif validation_status is False:
                # Patient not found
                context_data["db_error"] = validation_error
                context_data["sources"] = []
                logger.warning(f"Patient ID validation failed: {validation_error}")
            elif validation_status is True:
                # Patient exists, proceed with query
                try:
                    patient_data = self.sql_agent.query_patient_record(patient_id)
                    context_data["patient_data"] = patient_data
                    
                    # Validate if we actually have usable data
                    validation_result = self.validation_agent.validate_context_data(
                        context_data, intent, patient_id
                    )
                    
                    if validation_result["is_valid"]:
                        context_data["sources"] = validation_result["sources"]
                        logger.info(f"Patient record retrieved for ID: {patient_id}")
                    else:
                        # Database connection failed or no data found
                        context_data["sources"] = []
                        context_data["db_error"] = validation_result["error_message"]
                        logger.warning(f"Patient record unavailable: {validation_result['error_message']}")
                        
                except Exception as e:
                    logger.error(f"Error querying patient record: {e}")
                    context_data["db_error"] = str(e)
                    context_data["sources"] = []

        # Query medications if MEDICATION_QUERY intent
        if intent == "MEDICATION_QUERY":
            # If doctor asked about medication for a specific patient, get patient data for dose calculation
            if patient_id and not context_data.get("patient_data"):
                validation_status, patient_info, validation_error = self.triage_agent.validate_patient_id(patient_id)
                if validation_status is True:
                    try:
                        patient_data = self.sql_agent.query_patient_record(patient_id)
                        context_data["patient_data"] = patient_data
                        logger.info(f"Patient data retrieved for medication dose calculation: {patient_id}")
                    except Exception as e:
                        logger.warning(f"Could not retrieve patient data for dose calc: {e}")
            
            try:
                med_results = self.mcp_agent.search_medication(user_question)
                if med_results and med_results.get('count', 0) > 0:
                    context_data["mcp_data"]["medications"] = med_results
                    context_data["sources"].append("Medication Database (Enhanced)")
                    
                    # If we have patient data, calculate dose
                    if context_data.get("patient_data"):
                        try:
                            patient_data = context_data["patient_data"]
                            
                            # Extract weight from vitals
                            weight_kg = None
                            if patient_data.get("vitals") and patient_data["vitals"].get("data"):
                                for vital in patient_data["vitals"]["data"]:
                                    vital_name = vital.get('vital_name', '').lower()
                                    if 'weight' in vital_name:
                                        weight_kg = vital.get('value_numeric')
                                        if weight_kg:
                                            break
                            
                            # Extract age from patient demographics
                            age_years = None
                            if patient_data.get("patient") and patient_data["patient"].get("data"):
                                p = patient_data["patient"]["data"][0]
                                birthdate = p.get('birthdate')
                                if birthdate:
                                    age_years = self.response_agent.calculate_age_from_birthdate(birthdate)
                            
                            if weight_kg and age_years is not None:
                                med_name = med_results["results"][0].get("name") if med_results.get("results") else None
                                if med_name:
                                    dose_result = self.mcp_agent.calculate_medication_dose(
                                        drug_name=med_name,
                                        weight_kg=float(weight_kg),
                                        age_years=float(age_years)
                                    )
                                    if dose_result and "error" not in dose_result:
                                        med_results["dose_calculation"] = dose_result
                                        logger.info(f"Dose calculated for {med_name}: {dose_result}")
                                        context_data["sources"].append("Patient Vitals (Weight) + FDA/RxNorm")
                        except Exception as e:
                            logger.debug(f"Dose calculation optional - skipped: {e}")
                    
                    logger.info(f"Medication data retrieved: {med_results['count']} results")
            except Exception as e:
                logger.error(f"Error searching medications: {e}")

        # Query vaccines if IMMUNIZATION_QUERY intent
        if intent == "IMMUNIZATION_QUERY":
            try:
                vac_results = self.mcp_agent.search_vaccine(user_question)
                if vac_results and vac_results.get('count', 0) > 0:
                    context_data["mcp_data"]["vaccines"] = vac_results
                    context_data["sources"].append("Immunization Database")
                    logger.info(f"Immunization data retrieved: {vac_results['count']} results")
            except Exception as e:
                logger.error(f"Error searching vaccines: {e}")

        # Query milestones if MILESTONE_QUERY intent
        if intent == "MILESTONE_QUERY":
            # CRITICAL FIX: Get patient age if patient selected
            patient_age = None
            if patient_id and not context_data.get("patient_data"):
                validation_status, patient_info, validation_error = self.triage_agent.validate_patient_id(patient_id)
                if validation_status is True:
                    try:
                        patient_data = self.sql_agent.query_patient_record(patient_id)
                        context_data["patient_data"] = patient_data
                        logger.info(f"Patient data retrieved for milestone query: {patient_id}")
                    except Exception as e:
                        logger.warning(f"Could not retrieve patient data for milestone: {e}")
            
            # Extract patient age from patient data
            if context_data.get("patient_data"):
                try:
                    patient_data = context_data["patient_data"]
                    if patient_data.get("patient") and patient_data["patient"].get("data"):
                        p = patient_data["patient"]["data"][0]
                        birthdate = p.get('birthdate')
                        if birthdate:
                            patient_age = self.response_agent.calculate_age_from_birthdate(birthdate)
                            logger.info(f"Patient age calculated: {patient_age} years for milestone query")
                except Exception as e:
                    logger.debug(f"Could not extract patient age: {e}")
            
            try:
                # Enhanced query with patient age context if available
                enhanced_milestone_query = user_question
                if patient_age is not None:
                    enhanced_milestone_query = f"{user_question} (Patient age: {patient_age} years)"
                
                milestone_results = self.mcp_agent.search_milestone(enhanced_milestone_query)
                if milestone_results and milestone_results.get('count', 0) > 0:
                    milestone_results["patient_age"] = patient_age
                    context_data["mcp_data"]["milestones"] = milestone_results
                    context_data["sources"].append("Milestone Database")
                    if patient_age is not None:
                        context_data["sources"].append(f"Patient Age ({patient_age} years)")
                    logger.info(f"Milestone data retrieved: {milestone_results['count']} results for {patient_age} years")
            except Exception as e:
                logger.error(f"Error searching milestones: {e}")

        # Query knowledge base
        try:
            if user_type == "DOCTOR":
                kb_results = self.knowledge_agent.query_doctor_kb(user_question)
                kb_content = self.knowledge_agent.format_context(kb_results)
            else:
                kb_results = self.knowledge_agent.query_patient_kb(user_question)
                kb_content = self.knowledge_agent.format_context(kb_results)

            if kb_content:
                context_data["sources"].append("Knowledge Base")
            context_data["kb_content"] = kb_content
        except Exception as e:
            logger.warning(f"Error querying knowledge base: {e}")
            context_data["kb_content"] = ""

        # Generate response
        try:
            # If this was a PATIENT_RECORD_QUERY and we have a database error, return error response
            if intent == "PATIENT_RECORD_QUERY" and context_data.get("db_error"):
                no_data_response = self.validation_agent.create_no_data_response(
                    context_data["db_error"]
                )
                response = self.format_response(no_data_response)
                logger.info(f"Returning error response due to database issue")
            # Special handling for milestone queries with patient age context
            elif intent == "MILESTONE_QUERY" and context_data.get("mcp_data", {}).get("milestones"):
                response = self.response_agent.generate_milestone_response(
                    user_question,
                    context_data,
                    user_type=user_type
                )
            # Special handling for medication dose questions with patient context
            elif intent == "MEDICATION_QUERY" and user_type == "DOCTOR" and context_data.get("mcp_data", {}).get("medications"):
                response = self.response_agent.generate_medication_response_with_context(
                    user_question,
                    context_data
                )
            else:
                if user_type == "DOCTOR":
                    response = self.response_agent.generate_doctor_response(user_question, context_data)
                else:
                    response = self.response_agent.generate_patient_response(user_question, context_data)
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            response = "Unable to generate response at this time. Please try again."

        # Ensure sources never default to "Self-help" when data is unavailable
        final_sources = context_data["sources"]
        if not final_sources and context_data.get("db_error"):
            final_sources = ["No Data Available"]
        elif not final_sources:
            final_sources = ["Knowledge Base"]  # Only KB if patient query failed but no DB error

        result = {
            "timestamp": datetime.now().isoformat(),
            "user_type": user_type,
            "intent": intent,
            "question": user_question,
            "response": response,
            "sources": final_sources,
            "patient_id": patient_id
        }

        self.save_response(result)
        logger.info(f"Processing complete | Sources: {', '.join(result['sources'])}")
        return result

    def save_response(self, result):
        try:
            if os.path.exists(RESPONSES_FILE):
                with open(RESPONSES_FILE, 'r') as f:
                    responses = json.load(f)
            else:
                responses = []

            responses.append(result)

            with open(RESPONSES_FILE, 'w') as f:
                json.dump(responses, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save response: {str(e)}")

    def select_patient(self):
        """Interactive patient selection"""
        print("\n" + "="*60)
        print("PATIENT SELECTION")
        print("="*60)
        print("\nHow would you like to search for a patient?")
        print("1. Search by Patient ID (like 1000001W or numeric)")
        print("2. Search by Patient Name")
        print("3. List all patients")
        
        choice = input("\nSelect option (1-3): ").strip()
        
        patient_id = None
        patient_data = None
        
        if choice == "1":
            patient_id = input("Enter Patient ID (e.g., 1000001W or 8): ").strip()
            # Accept both numeric and alphanumeric IDs
            if patient_id:
                result = self.sql_agent.db.connect()
                if result:
                    patient_result = self.sql_agent.db.verify_patient_exists(patient_id)
                    self.sql_agent.db.disconnect()
                    if patient_result and patient_result is not None and patient_result is not False:
                        patient_data = patient_result
                        actual_id = patient_result.get('patient_identifier', patient_result.get('patient_id', patient_id))
                        logger.info(f"Found patient: {actual_id}")
                    else:
                        print(f"[ERROR] No patient found with ID: {patient_id}")
                        return None, None
                else:
                    print("[ERROR] Could not connect to database")
                    return None, None
            else:
                print("[ERROR] Please enter a valid patient ID")
                return None, None
                
        elif choice == "2":
            patient_name = input("Enter Patient Name (First or Last): ").strip()
            if len(patient_name) < 2:
                print("[ERROR] Please enter at least 2 characters")
                return None, None
            
            result = self.sql_agent.db.connect()
            if result:
                search_result = self.sql_agent.db.search_patients(patient_name)
                self.sql_agent.db.disconnect()
                
                if search_result['data'] and len(search_result['data']) > 0:
                    print(f"\n[FOUND] {len(search_result['data'])} patient(s):")
                    for i, patient in enumerate(search_result['data'], 1):
                        full_name = self.format_full_name(patient)
                        patient_id_display = patient.get('patient_identifier', patient.get('patient_id', 'N/A'))
                        print(f"  {i}. ID: {patient_id_display:>10} | {full_name:25} | Gender: {patient.get('gender', 'N/A'):6} | DOB: {patient.get('birthdate', 'N/A')}")
                    
                    selection = input("\nSelect patient number (or 0 to go back): ").strip()
                    if selection.isdigit() and 0 < int(selection) <= len(search_result['data']):
                        selected = search_result['data'][int(selection) - 1]
                        # Use patient_identifier if available, otherwise use patient_id
                        patient_id = selected.get('patient_identifier', str(selected.get('patient_id')))
                        # Now get full patient details
                        result = self.sql_agent.db.connect()
                        if result:
                            patient_result = self.sql_agent.db.verify_patient_exists(patient_id)
                            self.sql_agent.db.disconnect()
                            if patient_result and patient_result is not False and patient_result is not None:
                                patient_data = patient_result
                                logger.info(f"Selected patient: {patient_id}")
                else:
                    print(f"[ERROR] No patients found matching: {patient_name}")
                    return None, None
                    
        elif choice == "3":
            result = self.sql_agent.db.connect()
            if result:
                search_result = self.sql_agent.db.list_all_patients(20)
                self.sql_agent.db.disconnect()
                
                if search_result['data']:
                    print(f"\nShowing first 20 patients:")
                    for i, patient in enumerate(search_result['data'][:20], 1):
                        full_name = self.format_full_name(patient)
                        patient_id_display = patient.get('patient_identifier', patient.get('patient_id', 'N/A'))
                        print(f"  {i:>2}. ID: {patient_id_display:>10} | {full_name:25} | {patient.get('gender', 'N/A'):6} | {patient.get('birthdate', 'N/A')}")
                    
                    selection = input("\nEnter patient ID to select (or 0 to go back): ").strip()
                    if selection and selection != "0":
                        patient_id = selection
                        result = self.sql_agent.db.connect()
                        if result:
                            patient_result = self.sql_agent.db.verify_patient_exists(patient_id)
                            self.sql_agent.db.disconnect()
                            if patient_result and patient_result is not False and patient_result is not None:
                                patient_data = patient_result
                                logger.info(f"Selected patient: {patient_id}")
                            else:
                                print(f"[ERROR] Could not load patient details")
                                return None, None
        else:
            print("[ERROR] Invalid option")
            return None, None
        
        return patient_id, patient_data

    def display_patient_details(self, patient_id, patient_data):
        """Display patient information"""
        if not patient_data:
            return
        
        print("\n" + "="*60)
        print("PATIENT DETAILS")
        print("="*60)
        # Display the proper patient identifier
        patient_id_display = patient_data.get('patient_identifier', patient_data.get('patient_id', patient_id))
        print(f"\nPatient ID: {patient_id_display}")
        print(f"Gender: {patient_data.get('gender', 'N/A')}")
        print(f"Birth Date: {patient_data.get('birthdate', 'N/A')}")
        print(f"Address: {patient_data.get('address1', 'N/A')}")
        if patient_data.get('address2'):
            print(f"         {patient_data.get('address2')}")
        print(f"City: {patient_data.get('city_village', 'N/A')}")
        print(f"State: {patient_data.get('state_province', 'N/A')}")
        print(f"Postal Code: {patient_data.get('postal_code', 'N/A')}")
        print(f"Status: {'Deceased (' + patient_data.get('death_date', '') + ')' if patient_data.get('dead') else 'Active'}")
        print("="*60)

    def run_interactive(self):
        logger.info("Interactive session started")
        
        # First, ask user to select their role
        self.select_user_role()
        
        while True:
            # Then, select a patient
            patient_id, patient_data = self.select_patient()
            
            if not patient_id:
                print("\n[INFO] Exiting chatbot.")
                break
            
            # Display patient details
            self.display_patient_details(patient_id, patient_data)
            
            # Get full patient details from database
            patient_full_info = self.sql_agent.query_patient_record(patient_id)
            
            # Now ask queries about this patient
            print("\n" + "="*60)
            print(f"QUERYING PATIENT: {patient_id}")
            print("="*60)
            print("Ask questions about this patient's medical records")
            print("Examples:")
            print("  - What are the recent observations for this patient?")
            print("  - Show me the patient's encounters")
            print("  - What conditions does this patient have?")
            print("\nCommands:")
            print("  'back'  - Select a different patient")
            print("  'exit'  - Exit the chatbot")
            print("="*60 + "\n")

            while True:
                user_input = input(f"[{self.user_role.upper()} | Patient {patient_id}] Your Question: ").strip()

                if user_input.lower() == 'exit':
                    print("Thank you for using the Clinical Chatbot. Goodbye!")
                    return

                if user_input.lower() == 'back':
                    print("\nGoing back to patient selection...\n")
                    break

                if not user_input:
                    print("Please enter a question.")
                    continue

                # Pass selected patient context directly to process_query
                result = self.process_query(user_input, selected_patient_id=patient_id)


                print("\n" + "-" * 60)
                print(f"User Type: {result['user_type']}")
                print(f"Intent: {result['intent']}")
                print(f"Patient ID: {result.get('patient_id', patient_id)}")
                print(f"Sources: {', '.join(result['sources'])}")
                print("-" * 60)
                print("\nResponse:")
                print(result['response'])
                print("-" * 60)


def main():
    logger.info("Clinical Chatbot Started")
    chatbot = ClinicalChatbot()

    import sys
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        result = chatbot.process_query(question)
        print("\n" + "=" * 60)
        print(f"User Type: {result['user_type']}")
        print(f"Intent: {result['intent']}")
        print(f"Sources: {', '.join(result['sources'])}")
        print("=" * 60)
        print("\nResponse:")
        print(result['response'])
        print("=" * 60)
    else:
        chatbot.run_interactive()


if __name__ == "__main__":
    main()