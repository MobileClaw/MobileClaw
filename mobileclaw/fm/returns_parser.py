#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import json
import types
from typing import List, Any
import structlog
from ..utils.interface import UniInterface

logger = structlog.get_logger(__name__)

# Type definitions
TypeList = List
JsonAnswer = List
TypeAlias = str | type | types.GenericAlias

# Basic and complex type definitions
basic_types = [str, int, float, bool]
complex_types = [list, tuple, dict, set]
basic_types_dict = {t.__name__: t for t in basic_types}
complex_types_dict = {t.__name__: t for t in complex_types}

class ReturnsParser(UniInterface):
    """Class for parsing and formatting model return values."""

    def __init__(self, agent):
        super().__init__(agent)
        self._tag = 'fm.returns_parser'
        self.task_language = self.agent.config.task_language

    def _generate_exmaple(self, type_list: TypeList, indent: int) -> str:
        """Generate an example for the type list.

        Args:
            type_list: Type list
            indent: Indentation level

        Returns:
            str: Example string
        """
        if type(type_list) is type:
            type_list = [type_list]
        if len(type_list) == 1:
            if type_list[0] in basic_types:
                if type_list[0] is str:
                    return '\t'*indent+'"a string"\n'
                elif type_list[0] is int:
                    return '\t'*indent+'123\n'
                elif type_list[0] is float:
                    return '\t'*indent+'123.456\n'
                elif type_list[0] is bool:
                    return '\t'*indent+'true\n'
            else:
                logger.debug("Unsupported type", action='generate_example', status='continue')
                return '\t'*indent+'[]\n'
        else:
            if type_list[0] is list:
                curr_ans=self._generate_exmaple(type_list[1:],indent+1)
                curr_ans=curr_ans[:-1]+',\n'
                comment = "# I've put three elements here, the actual number depends on the situation\n"
                return '\t'*indent+'[\n'+curr_ans*3+'\t'*(indent+1)+comment+'\t'*indent+']\n'
            elif type_list[0] is tuple:
                ans='\t'*indent+'[\n'
                for i in range(len(type_list[1])):
                    ans+=self._generate_exmaple(type_list[1][i],indent+1)
                    ans=ans[:-1]+",\n"
                ans=ans[:-2]+'\n'+'\t'*indent+']\n'
                return ans
            elif type_list[0] is dict:
                ans='\t'*indent+'{\n'
                curr_ans=""
                curr_ans+='\t'*indent+'\"key\":\n'
                curr_ans+=self._generate_exmaple(type_list[1:],indent+1)
                curr_ans=curr_ans[:-2]+',\n'
                ans+=curr_ans*3
                comment = "# I've put three key-value pairs here, the actual number depends on the situation\n"
                ans+='\t'*indent+comment
                ans+='\t'*indent+'}\n'
                return ans
            else:
                logger.debug("Unsupported type", action='generate_example', status='continue')
                return '\t'*indent+'[]\n'

    def generate_example(self, required_values: List[tuple[str,TypeList]]) -> str:
        """
        Generate examples for required values

        Parameters
        ----------
        required_values : List[tuple[str,TypeList]]
            List of required values, each item is a tuple containing a description and a type list

        Returns
        -------
        str
            Example string
        """
        example = "[\n"
        for i in range(len(required_values)):
            if self.task_language == "zh":
                example += f'\t# 第{i+1}项内容应该是{required_values[i][0]},它的类型应该是{self.type_list_to_prompt(required_values[i][1])}\n'
            else:
                example += f'\t# The {i+1}th item should be {required_values[i][0]}, its type should be {self.type_list_to_prompt(required_values[i][1])}\n'
            example += self._generate_exmaple(required_values[i][1], indent=1)
        example += "]\n"
        return example

    def get_returns(self, returns: TypeAlias) -> List[tuple[str, TypeList]]:
        """
        Convert types from str, type, types.GenericAlias to list

        Parameters
        ----------
        returns : TypeAlias
            Can be basic types or composite types

        Returns
        -------
        List[tuple[str, TypeList]]
            List of tuples containing description and type list
        """
        requiredValues = []
        if returns is None:
            # logger.debug("No return type received", action='parse_type', status='continue')
            requiredValues = [("", [str])]
        elif type(returns) is str:
            # Only one string, indicating this string is a description, default type is string
            requiredValues = [(returns, [str])]
        elif type(returns) is tuple:
            # Only one tuple, indicating only one expected return value, the first content is its description followed by its type
            if len(returns) == 2:
                requiredValues = [(returns[0], self.parse_string_to_type_list(returns[1]))]
            elif len(returns) == 1:
                requiredValues = [(returns[0], [str])]
            else:
                logger.debug("")
                requiredValues = [(str(returns), [str])]
        elif type(returns) is list:
            for ret in returns:
                if type(ret) is str:
                    requiredValues.append((ret, [str]))
                elif type(ret) is tuple:
                    if len(ret) == 2:
                        requiredValues.append((ret[0], self.parse_string_to_type_list(ret[1])))
                    elif len(ret) == 1:
                        requiredValues.append((ret[0], [str]))
                    else:
                        logger.debug("")
                        requiredValues.append((str(ret), [str]))
                else:
                    logger.debug("Incorrect parameter type in returns list! This item will be used as description, return type forced to str")
                    requiredValues.append((str(ret), [str]))
        else:
            logger.debug("Incorrect parameter type! Will be used as description, return type forced to str")
            requiredValues = [(str(returns), [str])]
        return requiredValues

    def type_list_to_prompt(self, typeList: TypeList) -> str:
        """
        Convert type list to prompt string

        Parameters
        ----------
        typeList : TypeList
            Type list

        Returns
        -------
        str
            Prompt string representing the type list
        """
        if len(typeList) == 1:
            return typeList[0].__name__
        if typeList[0] is list:
            return f"An array, where each item is a {self.type_list_to_prompt(typeList[1:])}"
        elif typeList[0] is dict:
            return f"A dictionary, where its value is {self.type_list_to_prompt(typeList[1:])}"
        elif typeList[0] is tuple:
            tupleLength = str(len(typeList[1]))
            tupleDetails = ""
            for i in range(len(typeList[1])):
                tupleDetails += f"The {i + 1}th item is a {self.type_list_to_prompt(typeList[1][i])}"

            return f"A tuple, which you will return as a list, but you should understand that this tuple has a fixed length of {tupleLength}, where {tupleDetails}"

    def _string_to_type_list(self, typeStr: str) -> TypeList:
        """
        Convert type string to type list

        Parameters
        ----------
        typeStr : str
            Type string

        Returns
        -------
        TypeList
            Type list
        """
        if '[' not in typeStr:
            typeStr = typeStr.replace(']', '')
            typeStr = typeStr.replace(',', '')
            if typeStr in basic_types_dict.keys():
                return [basic_types_dict[typeStr]]
            elif typeStr in complex_types_dict.keys():
                return [complex_types_dict[typeStr], str]
            else:
                logger.debug("Invalid type: %s, assume to be str" % typeStr, action='parse_type', status='continue')
                return [str]
        else:
            currType = typeStr[:typeStr.index('[')]
            if currType in basic_types_dict.keys():
                logger.debug("Basic types cannot be expanded further, assume to be str", action='parse_type', status='continue')
                return [str]
            elif currType in complex_types_dict.keys():
                if currType == 'dict':
                    currType = dict
                    # In JSON, only string is accepted as key type!
                    # https://www.json.org/json-en.html
                    return [dict] + self._string_to_type_list(typeStr[typeStr.index(',') + 1:-1])
                elif currType == 'tuple':
                    currType = tuple
                    typeStr = typeStr[typeStr.index('[') + 1:-1]
                    bracketLevel = 0
                    tupleElements = []
                    lastI = 0
                    for i in range(len(typeStr)):
                        c = typeStr[i]
                        if c == ',' and bracketLevel == 0:
                            if lastI < i:
                                tupleElements.append(typeStr[lastI:i])
                                lastI = i + 1
                            else:
                                logger.debug("Don't put two consecutive commas in a tuple!", action="tuple detection", status='continue')
                        if c == '[':
                            bracketLevel += 1
                        if c == ']':
                            bracketLevel -= 1
                            if bracketLevel < 0:
                                logger.debug("typeStr level error", action='typeStrParse', status='continue')
                                break
                    if lastI < len(typeStr):
                        tupleElements.append(typeStr[lastI:])
                    if len(tupleElements) == 0:
                        logger.debug("Error! Tuple must have content!", action="parse tuple", status='continue')
                        tupleElements = [str]
                    for i in range(len(tupleElements)):
                        tupleElements[i] = self._string_to_type_list(tupleElements[i])
                    return [tuple, tupleElements]
                else:
                    # set and list are both list
                    return [list] + self._string_to_type_list(typeStr[typeStr.index('[') + 1:-1])
            raise Exception("Unrecognized type")

    def parse_string_to_type_list(self, typeStr: TypeAlias) -> TypeList:
        """
        Convert type alias to type list

        Parameters
        ----------
        typeStr : TypeAlias
            Type alias

        Returns
        -------
        TypeList
            Type list
        """
        if type(typeStr) is type:
            typeStr = typeStr.__name__
        elif type(typeStr) is types.GenericAlias:
            typeStr = str(typeStr)
        elif type(typeStr) is str:
            pass
        else:
            logger.debug("Unclear type", action='check type', status='continue')
            typeStr = str(typeStr)
        typeStr = typeStr.lower()
        typeStr = typeStr.replace(' ', '')
        return self._string_to_type_list(typeStr)

    def parse_string_to_json(self, response: str) -> List | None:
        """
        Extract JSON data from response string

        Parameters
        ----------
        response : str
            Response string that may contain JSON data

        Returns
        -------
        List | None
            Parsed JSON data or None
        """
        data = None
        if '```' in response:
            result = response.split('```')
            data = None
            for r in result:
                try:
                    if r.startswith('json'):
                        r = r[len('json'):]
                    data = json.loads(r)

                except json.decoder.JSONDecodeError:
                    pass
            if data is None:
                return None
        else:
            try:
                data = json.loads(response)
            except json.decoder.JSONDecodeError:
                return None
        return data

    def json_type_check(self, raw: Any, requiredValues: TypeList) -> tuple[bool, float]:
        """
        Check if JSON data conforms to the types specified in requiredValues

        Parameters
        ----------
        raw : Any
            JSON data to check
        requiredValues : TypeList
            Type list that JSON data is checked against

        Returns
        -------
        tuple[bool, float]
            Tuple containing a boolean indicating whether the check passed, and a score indicating the degree of success
        """
        curr = requiredValues[0]
        if curr in basic_types:
            if curr is str:
                if type(raw) is str:
                    return True, 1
                else:
                    return False, 0
            elif curr is float:
                if type(raw) is float:
                    return True, 1
                elif type(raw) is int:
                    # Allow int to be treated as float
                    return True, 1
                else:
                    return False, 0
            elif curr is int:
                if type(raw) is int:
                    return True, 1
                else:
                    return False, 0
            elif curr is bool:
                if type(raw) is bool:
                    return True, 1
                else:
                    return False, 0
            logger.error("Model return value type error")
            return False, 0
        if curr in complex_types:
            if curr is list or curr is set:
                if type(raw) is list:
                    if len(raw) == 0:
                        return True, 1.0
                    good = True
                    sumScore = 0
                    for i in raw:
                        anonGood, anonScore = self.json_type_check(i, requiredValues[1:])
                        good &= anonGood
                        sumScore += anonScore
                    return good, sumScore / len(raw) + 1
                else:
                    return False, 0
            elif curr is dict:
                if type(raw) is dict:
                    if len(raw) == 0:
                        return True, 1.0
                    good = True
                    sumScore = 0
                    for i in raw.values():
                        anonGood, anonScore = self.json_type_check(i, requiredValues[1:])
                        good &= anonGood
                        sumScore += anonScore
                    return good, sumScore / len(raw) + 1
                else:
                    return False, 0
            elif curr is tuple:
                if type(raw) is list:
                    if len(requiredValues) == 1:
                        logger.error("Model return value type error")
                        return False, 0
                    if len(raw) == len(requiredValues[1]):
                        if len(raw) == 0:
                            return True, 1.0
                        good = True
                        sumScore = 0
                        for i in range(len(raw)):
                            anonGood, anonScore = self.json_type_check(raw[i], requiredValues[1][i])
                            good &= anonGood
                            sumScore += anonScore
                        return good, sumScore / len(raw) + 1
                    else:
                        return False, 0.5
                else:
                    return False, 0
            else:
                logger.error("Model return value type error")
                return False, 0
        logger.error("Model return value type error")
        return False, 0

    def parse_json(self, answer: JsonAnswer, requiredValues: List[tuple[str, TypeList]]) -> tuple[bool, float]:
        """
        Parse and validate JSON data according to the required values list

        Parameters
        ----------
        answer : JsonAnswer
            JSON data to parse and validate
        requiredValues : List[tuple[str, TypeList]]
            List of tuples, each tuple contains a key and a list of required types for that key

        Returns
        -------
        tuple[bool, float]
            Tuple containing a boolean indicating whether parsing and validation passed, and a score indicating the degree of success
        """
        if type(answer) is not list:
            answer = [answer]
        score = 0
        good = True
        if len(answer) != len(requiredValues):
            logger.info("🔁 LLM return value length does not match expected, retrying query to LLM")
            logger.debug("=" * 20 + "LLM Query return value length does not match expected" + "=" * 20)
            logger.debug(f"answer length: {len(answer)}")
            logger.debug(f"answer: ")
            logger.debug(answer)
            logger.debug(f"requiredValues length: {len(requiredValues)}")
            logger.debug(f"requiredValues: ")
            logger.debug(requiredValues)
            logger.debug("=" * 50)
            return False, score
        for i in range(len(answer)):
            anonGood, anonScore = self.json_type_check(answer[i], requiredValues[i][1])
            good &= anonGood
            score += anonScore
        return good, score

    def type_list_to_string(self, typeList: List) -> str:
        """
        Convert type list to string representation

        Parameters
        ----------
        typeList : List
            List representing type hierarchy

        Returns
        -------
        str
            String representation of nested types in typeList
        """
        if len(typeList) == 0:
            return "str"
        curr = typeList[0]
        if curr in basic_types:
            return curr.__name__
        if type(curr) is list:
            anon = ""
            for c in curr:
                anon += self.type_list_to_string(c) + ", "
            return anon[:-2]
        if curr is dict:
            return curr.__name__ + "[str," + self.type_list_to_string(typeList[1:]) + "]"
        if curr is list or curr is set or curr is tuple:
            return curr.__name__ + "[" + self.type_list_to_string(typeList[1:]) + "]"
        raise Exception("Unrecognized type")


