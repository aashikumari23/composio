#!/usr/bin/env python

import json
import os
import time
from beaupy.spinners import Spinner, BARS, DOTS
from rich.console import Console
from beaupy import select_multiple
import termcolor
import requests
import jinja2
from uuid import getnode as get_mac

from api import get_redirect_url_for_integration, get_url_for_composio_action, identify_user, list_tools, wait_for_tool_auth_completion

console = Console()

ACCESS_TOKEN = "COMPOSIO-X3125-ZUA-1"
SKILLS_FILE = os.path.join(os.path.dirname(__file__), 'skills.json')

jinja2_env = jinja2.Environment(loader=jinja2.FileSystemLoader(''))
def get_autogen_skill_content_from_func_signature(skillRawId, skillId, skillTitle, skillDescription, skillFileName, toolName, functionSignature):
    template = jinja2_env.get_template('templates/skills.txt')
    descriptionComment = f"{skillTitle}\n# {skillDescription}"
    input_parameters = [];
    for parameter_name, parameter_info in functionSignature.get('Input', {}).get('properties', {}).items():
         input_parameters.append({
            "name": parameter_name,
            "type": get_python_types_from_json_types(parameter_info.get('type')),
            "description": parameter_info.get('description')
        })

    method_url = get_url_for_composio_action(toolName, actionName = skillRawId)
    rendered_template = template.render(method_url=method_url,description=descriptionComment, method_name=skillRawId, method_parameters=input_parameters)
    return rendered_template

def get_python_types_from_json_types(type: str):
    if type == "string":
        return "str"
    elif type == "integer":
        return "int"
    elif type == "number":
        return "float"
    elif type == "boolean":
        return "bool"
    elif type == "object":
        return "dict"
    elif type == "array":
        return "list"
    else:
        return "Any"

def get_autogen_tools_from_composio_tools(composio_tools):
    autogen_tools = {}
    for tool in composio_tools["tools"]:
        name = tool.get('Name')
        skills = [];
        for skill in tool.get('Actions', []):
            skillId = f"{name}-{skill.get('Id')}"
            skillTitle = f"{name}: {skill.get('DisplayName')}"
            skillDescription = skill.get('Description')
            skillFileName = f"{skillId}.py"
            skillRawId = skill.get('Id')
            function_signature = skill.get('Signature')
            skills.append({
                "id": skillId,
                "title": skillTitle,
                "description": skillDescription,
                "file_name": skillFileName,
                "content": get_autogen_skill_content_from_func_signature(skillRawId,skillId, skillTitle, skillDescription, skillFileName, name, function_signature)
            })
        autogen_tools[name] = skills
    return autogen_tools

def load_skills():
    composio_tools = list_tools()
    return get_autogen_tools_from_composio_tools(composio_tools)

def check_and_install(package_name):
    try:
        __import__(package_name)
    except ImportError:
        console.print(f"[yellow]{package_name} not installed. Installing...[/yellow]")
        os.system(f"pip install {package_name}")

def install_skills(dbManager):
    from autogenstudio.utils.dbutils import upsert_skill
    from autogenstudio.datamodel import Skill
    tools = load_skills()
    for toolKey, toolSkills in tools.items():
        for skillInfo in toolSkills:
            upsert_skill(skill=Skill(
                id=skillInfo["id"],
                content=skillInfo["content"],
                file_name=skillInfo["file_name"],
                title=skillInfo["title"],
                description=skillInfo["description"]
            ), dbmanager=dbManager)

def setup_autogen_studio():
    check_and_install('autogenstudio')
    from autogenstudio.utils.dbutils import DBManager
    import autogenstudio

    database_path = os.path.join(os.path.dirname(autogenstudio.__file__), "web/database.sqlite")
    return DBManager(path=database_path)

def print_intro(): 
        text = termcolor.colored('Composio', 'white', attrs=['bold'])  
        aiPlatformText = termcolor.colored('100+', 'green', attrs=['bold'])
        pinkEmojiText = termcolor.colored('hello@composio.dev', 'magenta', attrs=['bold'])
        boldNoteText = termcolor.colored('Note*', 'white', attrs=['bold'])
        print(f"""
┌───────────────────────────────────────────────────────────────────────────┐
│                                                                           │
│                           {text} <-> AutoGen                            │
│                                                                           │
│                     Plug {aiPlatformText} platforms in your agent                     │
│                                                                           │
│ {boldNoteText}: This package is in closed beta, please contact {pinkEmojiText}  │
│        to get early access.                                               │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
        """)

def save_user_id(user_id):
    user_data = {'user_id': user_id}
    with open('user_data.json', 'w') as outfile:
        json.dump(user_data, outfile)

def run_user_session_logic():
    spinner = Spinner(BARS, f"Authenticating you...")
    spinner.start()

    if os.path.exists('user_data.json'):
        time.sleep(1)
        console.print(f" [green]✔[/green]\n");
    else:
        try: 
            user_mac_address = get_mac()
            unique_identifier = f"{user_mac_address}-autogen"
            session_token = identify_user(unique_identifier)

            if session_token:
                console.print(f" [green]✔[/green]\n");
                save_user_id(session_token)

        except Exception as e:
            raise e
    
    spinner.stop()
    pass

def setup_integrations(integrations_selected):
    console.print(f"\n[green]> Setting up {len(integrations_selected)} integrations...[/green]\n")
    tools = list_tools()
    tools_map = {}
    for tool in tools["tools"]:
        tools_map[tool["Name"]] = tool

    for integration in integrations_selected:
        skillAgent = tools_map[integration]
        is_authenticated = skillAgent.get("Authentication", {}).get("isAuthenticated")
        # TODO: Check with actual API, if is_autenticated is really a string
        if is_authenticated == "False":
            auth_url = get_redirect_url_for_integration(integration.lower(), scopes=skillAgent.get("Authentication", {}).get("Scopes", []))
            spinner = Spinner(DOTS, f"[yellow]⚠[/yellow] {integration} requires authentication. Please visit the following URL to authenticate: {auth_url}")
            spinner.start()
            time.sleep(2)
            wait_for_tool_auth_completion(integration)
            console.print(f"[green]✔[/green] {integration} authenticated successfully!")
            spinner.stop()
    print("\n")
def run():
    try:
        print_intro()

        run_user_session_logic()

        spinner = Spinner(BARS, "Checking Requirements")
        spinner.start()
        check_and_install('autogen')
        db_manager = setup_autogen_studio()
        spinner.stop()
        console.print("[green]> All requirements are met... Good to go!\n[/green]")

        # access_token = input("Paste your beta access token here: ")
        # if access_token != ACCESS_TOKEN:
        #     console.print("[red]\n> Invalid access token ❌\n[/red]")
        #     return

        skills = load_skills()
        if skills:
            capitalized_integration_names = [name.capitalize() for name in skills]
            console.print("> Which integrations do you want to install?")
            integrations_selected = select_multiple(capitalized_integration_names, tick_character='■', ticked_indices=[0], maximal_count=100, cursor_style='bold', tick_style='green', pagination=True)
            setup_integrations(integrations_selected)
            spinner = Spinner(BARS, "Setting up your skills...")
            spinner.start()
            install_skills(db_manager)
            time.sleep(2)
            spinner.stop()
            console.print("[green]> All skills installed successfully! 🚀\n[/green]")
            from autogenstudio.cli import ui
            ui()
    except Exception as e:
        console.print(f"[red]Error occurred: {e}[/red]")

run()