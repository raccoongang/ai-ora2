"""
TODO: Add module description.
"""
import re
import logging


from django.conf import settings

from openassessment.assessment.api import staff as staff_api
from openassessment.assessment.errors import StaffAssessmentInternalError, StaffAssessmentRequestError
from openassessment.workflow import api as workflow_api
from openassessment.xblock import ai_processors

from .data_conversion import clean_criterion_feedback

logger = logging.getLogger(__name__)

AI_MODELS_LIST = {
    'gpt_model_processor': "Chat GPT",
    'davinci_model_processor': "Text-Davinci"
}


# TODO: Move methods like below to utils.
def format_prompts(rubric):  # TODO: Add docstring.
    prompts_text = ""

    options = rubric['options']

    for index, elem in enumerate(options):
        prompts_text += f"{index}: {elem['explanation']}\n"

    return prompts_text


def get_student_response_from_ai(question, answer, prompts, ai_prompt, ai_model):
    # Tag
    # openai.api_key = getattr(settings, 'OPENAI_API_KEY', "")  # TODO: Move to settings and get from there

    if ai_model in AI_MODELS_LIST.keys():
        if ai_processor := getattr(ai_processors, ai_model) if hasattr(ai_processors, ai_model) else None:


            messages = []


            prompt = ai_prompt.format(question=question, student_answer=answer, prompts=prompts)

            if ai_model == 'gpt_model_processor':
                messages = [
                    {"role": "system", "content":f"Instructor enters the following prompt for the ChatGPT: {ai_prompt}"},
                    {"role": "system", "content":f"The question to the student is: {question}."},
                    {"role": "system", "content":f"The rubric for grading student's response: {prompts}."},
                    {"role": "system", "content":f"Please select the most suited rubric number, and include phrase RUBRIC_OPTION_IS: rubric number, also please follow the prompt {ai_prompt}"},
                    {"role": "user", "content":f"My answer is: {answer}."},
                ]

            logger.info(f"{AI_MODELS_LIST.get(ai_model)} prompt")

            logger.info(prompt)
            return ai_processor(prompt, messages)


def process_ai_response(text):
    # import pdb; pdb.set_trace()
    regexp_expr = r"RUBRIC_OPTION_IS: (?:\d)\.?"  # TODO: Move to settings or config model.
    resp = re.findall(regexp_expr, text)

    # TODO: refactor for better catching errors and optimizations.
    try:
        response_option = int(''.join(filter(str.isdigit, resp[0])))
        response_explanation = text.split(resp[0])[-1].strip()
    except Exception:
        return None, None

    return response_option, response_explanation


# TODO: Move to config or Django config model.
# You are the teacher.
QUESTION_TEMPLATE = """
You are a cisco instructor, critque the answer based on wendell odems cisco press ccna book.
Question prompt is:
{question}\n
Student's answer is: {student_answer}.
Provide response in the format "RIGHT ANSWER IS": <most suitable choice here>.
Choose the most suitable choice from the following:
{prompts}
Write short (200 symbols) feedback about student answer points (What was correct and what was wrong).
Max response length should be up to 200 symbols.
"""

QUESTION_TEMPLATE1 = """
You are a cisco instructor, critique the answer based on wendell odems cisco press ccna book.
Question prompt is:
"{question}"\n
Responder's answer is: "{student_answer}".

Write answer in the format "GRADE FOR STUDENT ANSWER IS": <choice as a number from the rubric>
Rubric:
{prompts}\n
In addition write short feedback (200 words) about student answer points, what was correct and what was wrong.
"""

QUESTION_TEMPLATE2 = """
You are a NASA instructor, please grade reflection based on the rubric.
Question prompt is: "{question}"\n
Responder's answer is: "{student_answer}".

Write short feedback (200 words) about responders answer in first person, do not critique the answer, but respond empathetically.
"""


def generate_automatic_assessment(question, criterias, student_answer_data, student_id, rubric_dict, ai_completion,
                                  ai_model):
    # import pdb; pdb.set_trace()
    result_dict_data = {
        # 'options_selected': {'Ideas': 'Poor'},
        'options_selected': {},
        # 'criterion_feedback': {'Ideas': 'Це просто ужас. Таких студенів треба гнати з платформи.'},
        'criterion_feedback': {},
        'overall_feedback': '',
        'submission_uuid': student_answer_data['uuid'],
        'assess_type': 'full-grade'
    }

    # TODO: Process getting data for avoiding errors.

    student_answer_text = student_answer_data['answer']['parts'][0]['text']


    for criteria in criterias:
        prompts = format_prompts(criteria)
        response = get_student_response_from_ai(question, student_answer_text, prompts, ai_completion, ai_model)

        logger.info("Response from AI is: {}".format(response))
        if response:

            choice, explanation = process_ai_response(response)

            if not choice:
                choice = 0
                explanation = response

            if choice or explanation:
                # TODO: Refactor ??
                result_dict_data['options_selected'][criteria['name']] = criteria['options'][choice]['name']
                result_dict_data['criterion_feedback'][criteria['name']] = explanation

    data = result_dict_data

    if not result_dict_data['options_selected']:
        # Return here for avoiding settings the empty staff response
        return

    # Save as staff response.

    # TODO: Move code below to another method (logic separation is awesome feature)
    try:
        assessment = staff_api.create_assessment(
            data['submission_uuid'],
            student_id,
            data['options_selected'],
            clean_criterion_feedback(criterias, data['criterion_feedback']),
            data['overall_feedback'],
            rubric_dict,
        )
        assess_type = data.get('assess_type', 'regrade')
        workflow_api.update_from_assessments(
            assessment["submission_uuid"],
            None,
            override_submitter_requirements=(assess_type == 'regrade')
        )
    except StaffAssessmentRequestError:
        logger.warning(
            "An error occurred while submitting a staff assessment "
            "for the submission %s",
            data['submission_uuid'],
            exc_info=True
        )
        return False
    except StaffAssessmentInternalError:
        logger.exception(
            "An error occurred while submitting a staff assessment "
            "for the submission %s",
            data['submission_uuid']
        )
