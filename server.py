from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import sys
import io
import traceback
import inspect
from collections import deque

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# Store node functions and graph state
node_functions = {}
graph_state = {'nodes': {}, 'connections': []}

def create_node_function(code, node_name, node_id, inputs, outputs):
    """Create a callable function from the node's code."""
    input_names = [p.get('name', 'in') for p in inputs]
    output_names = [p.get('name', 'out') for p in outputs]

    print(f"Creating function for node: {node_name} (ID: {node_id})")
    print(f"Inputs: {input_names}")
    print(f"Outputs: {output_names}")

    # Create a namespace with the user's code
    namespace = {
        '__builtins__': __builtins__,
        'print': print,
        'len': len,
        'str': str,
        'int': int,
        'float': float,
        'list': list,
        'dict': dict,
        'tuple': tuple,
        'bool': bool,
        'sum': sum,
        'max': max,
        'min': min,
        'abs': abs,
        'sorted': sorted,
        'enumerate': enumerate,
        'zip': zip,
        'range': range,
        'map': map,
        'filter': filter,
        'traceback': traceback,
        'inspect': inspect,
    }

    # Execute the user's code in the namespace
    try:
        exec(code, namespace)
    except Exception as e:
        print(f"Error executing user code for node {node_name}: {e}")
        traceback.print_exc()
        return None

    # Find the user's function
    user_func = None

    # Try to find function named after the node
    if node_name in namespace and callable(namespace[node_name]):
        user_func = namespace[node_name]
        print(f"Found function: {node_name}")
    elif 'process' in namespace and callable(namespace['process']):
        user_func = namespace['process']
        print(f"Found function: process")
    else:
        # Look for any callable function
        for name, obj in namespace.items():
            if callable(obj) and not name.startswith('_'):
                user_func = obj
                print(f"Found function: {name}")
                break

    if user_func is None:
        print(f"No function found in code for node {node_name}")
        return None

    # Get the function's signature
    sig = inspect.signature(user_func)
    params = sig.parameters
    param_names = list(params.keys())

    print(f"Function parameters: {param_names}")

    # Create a wrapper that calls the user's function with the right arguments
    def wrapper(**kwargs):
        print(f"Wrapper received kwargs: {kwargs}")

        # Build arguments based on the function's parameters
        args = []
        for param_name in param_names:
            if param_name in kwargs:
                args.append(kwargs[param_name])
            else:
                # Use default value if available
                param = params[param_name]
                if param.default != inspect.Parameter.empty:
                    args.append(param.default)
                else:
                    args.append(None)

        print(f"Calling function with args: {args}")

        # Call the user's function
        result = user_func(*args)
        print(f"Function returned: {result}")

        # Ensure result is a dict
        if result is None:
            result = {}
        elif not isinstance(result, dict):
            if output_names:
                result = {output_names[0]: result}
            else:
                result = {"result": result}

        # Ensure all outputs are present
        for out_name in output_names:
            if out_name not in result:
                result[out_name] = None

        print(f"Final result: {result}")
        return result

    return wrapper

def build_execution_order(nodes, connections):
    """Build the execution order based on connections."""
    # Build adjacency list
    graph = {node_id: [] for node_id in nodes.keys()}
    in_degree = {node_id: 0 for node_id in nodes.keys()}

    for conn in connections:
        from_node = str(conn.get('from'))
        to_node = str(conn.get('to'))
        if from_node in graph and to_node in graph:
            graph[from_node].append(to_node)
            in_degree[to_node] = in_degree.get(to_node, 0) + 1

    # Topological sort (Kahn's algorithm)
    queue = deque([node_id for node_id in in_degree if in_degree[node_id] == 0])
    execution_order = []

    while queue:
        node_id = queue.popleft()
        execution_order.append(node_id)
        for neighbor in graph.get(node_id, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # If there are cycles, just return all nodes in original order
    if len(execution_order) != len(nodes):
        execution_order = list(nodes.keys())

    return execution_order

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/node/<int:node_id>/update_code', methods=['POST'])
def update_node_code(node_id):
    """Update a node's code."""
    data = request.json
    code = data.get('code', '')

    # Clear the cached function so it will be recompiled
    node_functions[node_id] = {
        'code': code,
        'function': None
    }

    return jsonify({'success': True, 'node_id': node_id})

@app.route('/node/<int:node_id>/execute', methods=['POST'])
def execute_node(node_id):
    """Execute a single node with given inputs."""
    data = request.json
    inputs = data.get('inputs', {})
    logs = []

    node_info = graph_state.get('nodes', {}).get(str(node_id))
    if not node_info:
        return jsonify({'error': f'Node {node_id} not found', 'logs': logs}), 404

    # Get or compile function
    node_data = node_functions.get(node_id)
    if node_data is None or node_data['function'] is None:
        func = create_node_function(
            node_info.get('code', ''),
            node_info.get('name', f'Node{node_id}'),
            node_id,
            node_info.get('inputs', []),
            node_info.get('outputs', [])
        )
        if func is None:
            return jsonify({'error': 'Failed to compile node function', 'logs': logs}), 500
        node_functions[node_id] = {'code': node_info.get('code', ''), 'function': func}

    func = node_functions[node_id]['function']

    # Execute
    try:
        stdout_capture = io.StringIO()
        sys.stdout = stdout_capture

        kwargs = {}
        for port in node_info.get('inputs', []):
            port_name = port.get('name', 'in')
            kwargs[port_name] = inputs.get(port_name, None)

        logs.append(f"Calling function with kwargs: {kwargs}")
        if not kwargs:
            result = func()
        else:
            result = func(**kwargs)

        sys.stdout = sys.__stdout__
        output = stdout_capture.getvalue()

        if result is None:
            result = {}

        logs.append(f"Execution completed. Result: {result}")
        if output:
            logs.append(f"stdout: {output.strip()}")

        return jsonify({
            'success': True,
            'output': result,
            'stdout': output,
            'logs': logs
        })
    except Exception as e:
        sys.stdout = sys.__stdout__
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc(),
            'logs': logs
        }), 500

    @app.route('/graph/execute', methods=['POST'])
    def execute_graph():
        """Execute the entire graph based on connections."""
        data = request.json
        nodes = data.get('nodes', {})
        connections = data.get('connections', {})

        logs = []  # store all log messages
        def log(msg):
            logs.append(msg)
            print(msg)  # still print to terminal

        log("=" * 60)
        log("GRAPH EXECUTION START")
        log(f"Nodes: {list(nodes.keys())}")
        log(f"Connections: {connections}")
        log("=" * 60)

        # Update graph state
        graph_state['nodes'] = nodes
        graph_state['connections'] = connections

        # Clear and rebuild node functions for this execution
        for node_id in nodes:
            node_functions.pop(int(node_id), None)

        # Build execution order
        execution_order = build_execution_order(nodes, connections)
        log(f"Execution order: {execution_order}")

        node_outputs = {}
        node_stdout = {}
        node_logs = {}  # store per-node logs

        for node_id in execution_order:
            node_info = nodes.get(node_id)
            if not node_info:
                continue

            node_id_int = int(node_id)
            node_logs[node_id] = []

            # Collect inputs from connections
            kwargs = {}
            for conn in connections:
                if str(conn.get('to')) == node_id:
                    from_node_id = str(conn.get('from'))
                    from_port = conn.get('fromPort')
                    to_port = conn.get('toPort')
                    log(f"Processing connection: {from_node_id}.{from_port} -> {node_id}.{to_port}")

                    if from_node_id in node_outputs:
                        from_outputs = node_outputs[from_node_id]
                        log(f"Source outputs: {from_outputs}")
                        if from_port in from_outputs:
                            kwargs[to_port] = from_outputs[from_port]
                            log(f"Mapped {to_port} = {from_outputs[from_port]}")
                        else:
                            log(f"WARNING: {from_port} not found in {from_outputs}")
                            log(f"Available outputs: {list(from_outputs.keys())}")
                            kwargs[to_port] = None
                    else:
                        log(f"WARNING: {from_node_id} not yet executed or no output")
                        kwargs[to_port] = None

            log(f"Node {node_id} kwargs: {kwargs}")

            # Get or compile function
            node_data = node_functions.get(node_id_int)
            if node_data is None or node_data['function'] is None:
                func = create_node_function(
                    node_info.get('code', ''),
                    node_info.get('name', f'Node{node_id}'),
                    node_id_int,
                    node_info.get('inputs', []),
                    node_info.get('outputs', [])
                )
                if func is None:
                    node_outputs[node_id] = {'error': 'Failed to compile node function'}
                    node_logs[node_id].append('ERROR: Failed to compile node function')
                    continue
                node_functions[node_id_int] = {'code': node_info.get('code', ''), 'function': func}

            func = node_functions[node_id_int]['function']

            # Execute the node
            try:
                stdout_capture = io.StringIO()
                sys.stdout = stdout_capture

                log(f"Calling function with kwargs: {kwargs}")
                result = func(**kwargs) if kwargs else func()

                sys.stdout = sys.__stdout__
                output = stdout_capture.getvalue()

                if result is None:
                    result = {}

                # Ensure all outputs are present
                outputs_list = node_info.get('outputs', [])
                if outputs_list:
                    for port in outputs_list:
                        port_name = port.get('name', 'out')
                        if port_name not in result:
                            result[port_name] = None

                node_outputs[node_id] = result
                node_stdout[node_id] = output
                node_logs[node_id].append(f"Execution completed. Output: {result}")
                if output:
                    node_logs[node_id].append(f"stdout: {output.strip()}")

            except Exception as e:
                sys.stdout = sys.__stdout__
                error_msg = str(e)
                traceback_str = traceback.format_exc()
                log(f"Error executing node {node_id}: {error_msg}")
                log(traceback_str)
                node_outputs[node_id] = {
                    'error': error_msg,
                    'traceback': traceback_str
                }
                node_stdout[node_id] = ''
                node_logs[node_id].append(f"ERROR: {error_msg}")

        log("=" * 60)
        log(f"Final outputs: {node_outputs}")
        log("=" * 60)

        return jsonify({
            'success': True,
            'outputs': node_outputs,
            'stdout': node_stdout,
            'logs': logs,           # full graph logs
            'node_logs': node_logs  # per-node logs
        })

@app.route('/graph/state', methods=['POST'])
def update_graph_state():
    """Update the full graph state."""
    data = request.json
    graph_state['nodes'] = data.get('nodes', {})
    graph_state['connections'] = data.get('connections', [])

    # Also compile all functions for faster execution
    for node_id, node_info in graph_state['nodes'].items():
        node_id_int = int(node_id)
        if node_id_int not in node_functions:
            func = create_node_function(
                node_info.get('code', ''),
                node_info.get('name', f'Node{node_id}'),
                node_id_int,
                node_info.get('inputs', []),
                node_info.get('outputs', [])
            )
            if func:
                node_functions[node_id_int] = {
                    'code': node_info.get('code', ''),
                    'function': func
                }

    return jsonify({'success': True})

@app.route('/graph/state', methods=['GET'])
def get_graph_state():
    """Get the current graph state."""
    return jsonify(graph_state)

@app.route('/graph/compile', methods=['POST'])
def compile_graph():
    """Compile all node functions."""
    data = request.json
    nodes = data.get('nodes', {})

    for node_id, node_info in nodes.items():
        node_id_int = int(node_id)
        code = node_info.get('code', '')
        func = create_node_function(
            code,
            node_info.get('name', f'Node{node_id}'),
            node_id_int,
            node_info.get('inputs', []),
            node_info.get('outputs', [])
        )
        if func:
            node_functions[node_id_int] = {
                'code': code,
                'function': func
            }

    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
