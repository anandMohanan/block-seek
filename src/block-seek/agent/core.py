import re
from typing import List, Dict, Any, Optional, Union
import logging
from langchain_openai import AzureChatOpenAI

from langchain.agents import Tool, AgentExecutor, LLMSingleActionAgent
from langchain.memory import ConversationBufferMemory
from langchain.prompts import BaseChatPromptTemplate
from langchain.schema import AgentAction, AgentFinish, HumanMessage, SystemMessage, AIMessage
from langchain.tools import BaseTool
from langchain.chains import LLMChain
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import AgentOutputParser
from langchain_core.runnables import RunnablePassthrough, Runnable
from langchain.tools import StructuredTool

import json

from pydantic import BaseModel, Field

from tools.wallet import WalletTool
from tools.token import TokenTool
from tools.nft import NFTTool
from tools.defi import DeFiTool
from tools.knowledge import KnowledgeTool
from config.settings import get_settings
from .prompts import SYSTEM_PROMPT, HUMAN_PROMPT, format_tool_descriptions

logger = logging.getLogger(__name__)
settings = get_settings()

class EntityContext(BaseModel):
    """Model for storing entity context"""
    last_address: Optional[str] = Field(default=None, description="Last analyzed Ethereum address")
    
class EnhancedConversationMemory(ConversationBufferMemory, BaseModel):
    """Enhanced memory class that tracks entity context"""
    
    entity_context: EntityContext = Field(default_factory=EntityContext)
    
    class Config:
        arbitrary_types_allowed = True

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> None:
        """Save context and extract entities"""
        super().save_context(inputs, outputs)
        
        # Extract and save any Ethereum addresses from the input
        query = inputs.get("input", "").lower()
        import re
        eth_addresses = re.findall(r'0x[a-fA-F0-9]{40}', query)
        
        if eth_addresses:
            self.entity_context.last_address = eth_addresses[0]

    def get_context(self) -> Dict[str, Any]:
        """Get current context including entities"""
        return {
            "chat_history": self.load_memory_variables({})["chat_history"],
            "entity_context": self.entity_context.dict()
        }


class Web3AgentPrompt(BaseChatPromptTemplate, BaseModel):
    """Custom prompt template for Web3 agent"""
    
    input_variables: List[str] = ["input", "chat_history", "agent_scratchpad"]
    prompt: ChatPromptTemplate = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", HUMAN_PROMPT),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

    def format_messages(self, **kwargs) -> List[Any]:
        """Format the prompt messages"""
        # Ensure required variables exist
        kwargs.setdefault("chat_history", [])
        kwargs.setdefault("agent_scratchpad", [])
        
        if "input" not in kwargs:
            raise ValueError("Missing required input variable: input")
            
        return self.prompt.format_messages(**kwargs)

    class Config:
        """Pydantic config"""
        arbitrary_types_allowed = True

class Web3Agent:
    """Core Web3 intelligence agent"""

    def __init__(self):
        self.llm = AzureChatOpenAI(
            azure_deployment=settings.AZURE_DEPLOYMENT,
            model_name=settings.MODEL_NAME,
            temperature=settings.TEMPERATURE,
            api_key=settings.AZURE_API_KEY,
            azure_endpoint=settings.AZURE_ENDPOINT,
            api_version=settings.AZURE_API_VERSION
        )
        
        self.memory = EnhancedConversationMemory(
            memory_key="chat_history",
            return_messages=True
        )
        
        self.tools = self._initialize_tools()
        self.agent_executor = self._create_agent_executor()

    def _initialize_tools(self) -> List[Tool]:
        """Initialize all analysis tools with structured input handling"""
        try:
            tools = []
            tool_classes = [
                WalletTool,
                TokenTool,
                NFTTool,
                KnowledgeTool
            ]
            
            for tool_class in tool_classes:
                try:
                    tool_instance = tool_class()
                    # Convert to StructuredTool
                    tools.append(
                        StructuredTool(
                            name=tool_instance.name,
                            description=tool_instance.description,
                            func=tool_instance.execute,
                            args_schema=tool_instance.get_parameters(),  # This should return a Pydantic model
                            coroutine=tool_instance.execute  # For async support
                        )
                    )
                except Exception as e:
                    logger.error(f"Failed to initialize {tool_class.__name__}: {str(e)}")
                    continue

            if not tools:
                raise RuntimeError("No tools were successfully initialized")
            return tools
            
        except Exception as e:
            logger.error(f"Failed to initialize tools: {str(e)}")
            raise

    def _create_agent_executor(self) -> AgentExecutor:
        """Create the agent executor using modern LangChain patterns"""
        try:
            print("\n=== Starting Agent Executor Creation ===")
            
            # Create tool descriptions string
            tool_descriptions = "\n".join([
                f"- {tool.name}: {tool.description}"
                for tool in self.tools
            ])
            print(f"\nInitialized Tools: {[tool.name for tool in self.tools]}")
            print(f"\nTool Descriptions:\n{tool_descriptions}")

            # Create the prompt template
            prompt = ChatPromptTemplate.from_messages([
                ("system", SYSTEM_PROMPT.format(tool_descriptions=tool_descriptions)),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad")
            ])
            print("\nPrompt Template Created")

            # Create the chain that will format intermediate steps
            def format_intermediate_steps(steps):
                print(f"\n=== Formatting Intermediate Steps ===")
                print(f"Steps received: {steps}")
                if not steps:
                    return []
                messages = []
                for action, observation in steps:
                    print(f"\nAction: {action}")
                    print(f"Action log: {action.log}")
                    print(f"Observation: {observation}")
                    messages.extend([
                        AIMessage(content=action.log),
                        HumanMessage(content=f"Observation: {observation}")
                    ])
                print(f"\nFormatted Messages: {messages}")
                return messages

            # Create the runnable agent chain
            def debug_chat_history(x):
                print(f"\n=== Debug Chat History ===")
                print(f"Input x: {x}")
                history = x.get("chat_history", [])
                print(f"Retrieved history: {history}")
                return history

            def debug_scratchpad(x):
                print(f"\n=== Debug Scratchpad ===")
                print(f"Input x: {x}")
                steps = x.get("intermediate_steps", [])
                print(f"Steps before formatting: {steps}")
                formatted = format_intermediate_steps(steps)
                print(f"Formatted steps: {formatted}")
                return formatted

            agent_chain = (
                RunnablePassthrough()
                .assign(
                    chat_history=debug_chat_history,
                    agent_scratchpad=debug_scratchpad
                )
                | prompt
                | self.llm
                | Web3AgentOutputParser()
            )
            print("\nAgent Chain Created")

            # Add debug wrapper to tools
            def tool_debug_wrapper(tool):
                original_execute = tool.func
                async def wrapped_execute(*args, **kwargs):
                    print(f"\n=== Tool Execution: {tool.name} ===")
                    print(f"Args: {args}")
                    print(f"Kwargs: {kwargs}")
                    try:
                        result = await original_execute(*args, **kwargs)
                        print(f"Tool Result: {result}")
                        return result
                    except Exception as e:
                        print(f"Tool Error: {str(e)}")
                        raise
                tool.func = wrapped_execute
                tool.coroutine = wrapped_execute
                return tool

            wrapped_tools = [tool_debug_wrapper(tool) for tool in self.tools]
            print(f"\nWrapped tools: {[tool.name for tool in wrapped_tools]}")

            # Create the executor
            executor = AgentExecutor(
                agent=agent_chain,
                tools=wrapped_tools,
                memory=self.memory,
                verbose=settings.DEBUG,
                max_iterations=5,
                handle_parsing_errors=True
            )
            print("\n=== Agent Executor Created Successfully ===")
            return executor

        except Exception as e:
            print(f"\n!!! Error Creating Agent Executor: {str(e)}")
            logger.error(f"Failed to create agent executor: {str(e)}")
            raise


    async def process_query(self, query: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Process a user query with enhanced context handling"""
        try:
            # Format query with context and memory
            formatted_query = self._format_query_with_context(query, context or {})
            
            # Prepare input with the required variables
            input_data = {
                "input": formatted_query,
                "chat_history": self.memory.load_memory_variables({})["chat_history"]
            }

            response = await self.agent_executor.ainvoke(input_data)
            formatted_response = self._format_response(response.get("output", ""))
            
            # Save the context after successful execution
            self.memory.save_context(
                {"input": query},
                {"output": formatted_response.get("response", "")}
            )
            
            return formatted_response
            
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return self.format_error_response(e)


    def _format_query_with_context(self, query: str, context: Dict) -> str:
        """Enhanced query formatting with memory context"""
        # Get stored context
        memory_context = self.memory.get_context()
        
        # Add last known address if it exists and query seems to need it
        if ('address' not in query.lower() and 
            memory_context['entity_context']['last_address'] and
            any(word in query.lower() for word in ['it', 'that', 'the', 'this'])):
            
            address = memory_context['entity_context']['last_address']
            query = f"{query} for address {address}"
        
        # Add any additional context
        if context:
            context_str = "\n".join([f"{k}: {v}" for k, v in context.items()])
            query = f"{query}\nContext:\n{context_str}"
            
        return query

    def _format_response(self, response: str) -> Dict[str, Any]:
        """Format agent response"""
        try:
            if isinstance(response, str) and response.strip().startswith("{"):
                return json.loads(response)
            return {
                "status": "success",
                "response": response,
                "type": "text"
            }
        except json.JSONDecodeError:
            return {
                "status": "success",
                "response": response,
                "type": "text"
            }

    async def get_tool_descriptions(self) -> List[Dict[str, Any]]:
        """Get descriptions of all available tools"""
        return [
            tool.get_tool_description()
            for tool in self.tools
        ]

    async def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get conversation history"""
        messages = self.memory.chat_memory.messages
        return [
            {
                "role": "user" if isinstance(msg, HumanMessage) else "assistant",
                "content": msg.content
            }
            for msg in messages
        ]

    async def clear_memory(self) -> None:
        """Clear conversation memory"""
        self.memory.clear()

    async def update_settings(self, new_settings: Dict[str, Any]) -> None:
        """Update agent settings"""
        try:
            if "temperature" in new_settings:
                self.llm.temperature = new_settings["temperature"]
            
            if "max_tokens" in new_settings:
                self.llm.max_tokens = new_settings["max_tokens"]
            
            if "memory_k" in new_settings:
                self.memory.k = new_settings["memory_k"]
            
            if "tool_settings" in new_settings:
                for tool in self.tools:
                    if tool.name in new_settings["tool_settings"]:
                        await tool.update_settings(
                            new_settings["tool_settings"][tool.name]
                        )
            
            logger.info("Agent settings updated successfully")
            
        except Exception as e:
            logger.error(f"Failed to update settings: {str(e)}")
            raise

    @staticmethod
    def format_error_response(error: Exception) -> Dict[str, Any]:
        """Format error response"""
        return {
            "status": "error",
            "error": str(error),
            "error_type": error.__class__.__name__
        }

    def __str__(self) -> str:
        """String representation of the agent"""
        return f"Web3Agent(model={self.llm.model_name}, tools={len(self.tools)})"


    
class Web3AgentOutputParser(Runnable):
    """Parser for Web3Agent outputs extending Runnable"""
    
    def invoke(self, input: Any, config: Optional[Dict] = None) -> Union[AgentAction, AgentFinish]:
        """Synchronous invoke method required by Runnable"""
        if hasattr(input, 'content'):
            input = input.content
        return self.parse(input)

    async def ainvoke(
        self, input: Any, config: Optional[Dict] = None, **kwargs
    ) -> Union[AgentAction, AgentFinish]:
        """Asynchronous invoke method required by Runnable"""
        if hasattr(input, 'content'):
            input = input.content
        return self.parse(input)

    def parse(self, text: str) -> Union[AgentAction, AgentFinish]:
        """Parse text into agent action or finish"""
        if not isinstance(text, str):
            raise ValueError(f"Expected string input, got {type(text)}")

        # Clean the input text
        text = text.strip()
        
        # Check for Final Answer
        if "Final Answer:" in text:
            return AgentFinish(
                return_values={"output": text.split("Final Answer:")[-1].strip()},
                log=text
            )

        # Parse out the action and action input using more flexible regex
        action_match = re.search(r"Action: *(.*?)[\n$]", text)
        action_input_match = re.search(r"Action Input: *(.*?)(?:$|\n)", text, re.DOTALL)

        if not action_match or not action_input_match:
            raise ValueError(f"Could not parse LLM output: {text}")

        action = action_match.group(1).strip()
        action_input = action_input_match.group(1).strip()

        # Try to parse action_input as JSON if it looks like JSON
        if action_input.startswith('{') and action_input.endswith('}'):
            try:
                action_input = json.loads(action_input)
            except json.JSONDecodeError:
                pass  # Keep as string if JSON parsing fails

        return AgentAction(tool=action, tool_input=action_input, log=text)

def format_to_openai_messages(intermediate_steps):
    """Format intermediate steps to messages"""
    if not intermediate_steps:
        return []
        
    messages = []
    for action, observation in intermediate_steps:
        messages.extend([
            AIMessage(content=action.log),
            HumanMessage(content=f"Observation: {observation}")
        ])
    return messages