#!/usr/bin/env python3
import argparse
import json
from time import sleep, time
from prepare import save_interview
from jinja2 import Template
import litellm
import requests

def convert_params(params):
    # integrating liteLLM to provide a standard I/O interface for every LLM
    # see https://docs.litellm.ai/docs/providers for list of supported providers
    remap = { 'max_new_tokens': 'max_tokens', 'repetition_penalty': 'presence_penalty'}
    model_params = {}
    for k,v in params.items():
        if remap.get(k): k=remap[k]
        model_params[k] = v
    return model_params

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Interview executor for LiteLLM')
    parser.add_argument('--input', type=str, required=True, help='path to prepare*.ndjson from prepare stage')
    parser.add_argument('--model', type=str, default='openai/chatgpt', help='model to use')
    parser.add_argument('--apibase', type=str, help='api base url override')
    parser.add_argument('--runtime', type=str, help='override runtime (when using openai-compatible server)')
    parser.add_argument('--seed', type=int, default=42, help='random seed to use (helps determinism)')
    parser.add_argument('--params', type=str, required=True, help='parameter file to use')
    parser.add_argument('--delay', type=int, default=0, help='delay between questions (in seconds)')
    parser.add_argument('--templateout', type=str, help='output template')
    parser.add_argument('--stop', type=str, help='stop sequences list json')
    args = parser.parse_args()

    # Load params and init model
    params = convert_params(json.load(open(args.params)))
    litellm.drop_params=True
    model_name = args.model
    runtime = model_name.split('/')[0]
        
    # OpenAI custom base
    if args.apibase: 
        params['api_base'] = args.apibase
        if 'openai' in model_name:
            if not args.runtime: raise Exception("If apibase is set and model is openai/ you must also provide runtime.")
            runtime = args.runtime
        
        try:
            model_info = requests.get(args.apibase + 'v1/models').json()        
            args.model = model_info['data'][0]['id'].split('/')[-1].replace('.gguf','')
        except:
            pass

    if args.stop:
        params['stop'] = json.loads(args.stop)
        
    # Run interview
    output_template = Template(open(args.templateout).read()) if args.templateout else None
    for input_file in args.input.split(','):
        interview = [json.loads(line) for line in open(input_file)]
        results = []     

        for idx, challenge in enumerate(interview):
            print(f"{idx+1}/{len(interview)} {challenge['name']} {challenge['language']}")
            messages = [{'role': 'user', 'content': challenge['prompt']}]
            t0 = time()
            response = litellm.completion(model=model_name, messages=messages, seed=args.seed, **params)
            t1 = time()
            speed = response.usage.completion_tokens/(t1-t0)
            
            msg = response.choices[0].message
            answer = msg['content'] if isinstance(msg,dict) else msg.content
            answer = output_template.render(**challenge, Answer=answer) if output_template else answer            
            
            print()
            print(answer)
            print(f"PERF: {model_name} generated {response.usage.completion_tokens} tokens in {t1-t0:.2f}s, {speed:.2f} tok/sec")
            print()

            result = challenge.copy()
            result['answer'] = answer
            result['params'] = params
            result['model'] = args.model
            result['runtime'] = runtime

            results.append(result)

            if args.delay:
                sleep(args.delay)

        save_interview(input_file, 'none', args.params, args.model, results)
