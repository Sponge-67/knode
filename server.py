# ================================================================
# BACKEND SERVER (Flask) - Add this as a separate file: server.py
# ================================================================

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import sys
import io
import traceback
from functools import wraps

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# Store node functions and graph state
node_functions = {}
graph_state = {}

def create_node_function(code, node_name, node_id, inputs, outputs):
    """Create a callable function from the node's code."""
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
    }

    # Add port names as variables for the function
    port_names = []
    for port in inputs:
        port_names.append(port.get('name', 'in'))
    for port in outputs:
        port_names.append(port.get('name', 'out'))

    # Create the function
    function_code = f"""
def process({', '.join(port_names)}):
    # Node: {node_name} (ID: {node_id})
    # Inputs: {', '.join([p.get('name', 'in') for p in inputs])}
    # Outputs: {', '.join([p.get('name', 'out') for p in outputs])}

{code}

    # Return outputs as a dict
    return {{}}
"""

    try:
        exec(function_code, namespace)
        return namespace.get('process')
    except Exception as e:
        print(f"Error creating function for node {node_name}: {e}")
        return None

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/node/<int:node_id>/update_code', methods=['POST'])
def update_node_code(node_id):
    """Update a node's code."""
    data = request.json
    code = data.get('code', '')

    # Store the code in the node functions dictionary
    node_functions[node_id] = {
        'code': code,
        'function': None  # Will be compiled on next execution
    }

    return jsonify({'success': True, 'node_id': node_id})

@app.route('/node/<int:node_id>/execute', methods=['POST'])
def execute_node(node_id):
    """Execute a single node with given inputs."""
    data = request.json
    inputs = data.get('inputs', {})

    # Get or create the node function
    node_data = node_functions.get(node_id)
    if not node_data:
        return jsonify({'error': f'Node {node_id} not found'}), 404

    # Compile the function if not already compiled
    if node_data['function'] is None:
        # We need node info from the graph state
        node_info = graph_state.get('nodes', {}).get(str(node_id))
        if not node_info:
            return jsonify({'error': f'Node info for {node_id} not found'}), 404

        inputs_list = node_info.get('inputs', [])
        outputs_list = node_info.get('outputs', [])

        func = create_node_function(
            node_data['code'],
            node_info.get('name', 'Unknown'),
            node_id,
            inputs_list,
            outputs_list
        )

        if func is None:
            return jsonify({'error': 'Failed to compile node function'}), 500

        node_data['function'] = func

    # Execute the function
    try:
        # Capture stdout
        stdout_capture = io.StringIO()
        sys.stdout = stdout_capture

        # Prepare arguments
        args = []
        node_info = graph_state.get('nodes', {}).get(str(node_id), {})
        for port in node_info.get('inputs', []):
            port_name = port.get('name', 'in')
            args.append(inputs.get(port_name, None))

        # Execute
        result = node_data['function'](*args)

        # Restore stdout
        sys.stdout = sys.__stdout__
        output = stdout_capture.getvalue()

        # Handle result
        if result is None:
            result = {}

        return jsonify({
            'success': True,
            'output': result,
            'stdout': output,
            'node_id': node_id
        })
    except Exception as e:
        sys.stdout = sys.__stdout__
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc(),
            'node_id': node_id
        }), 500

@app.route('/graph/execute', methods=['POST'])
def execute_graph():
    """Execute the entire graph based on connections."""
    data = request.json
    nodes = data.get('nodes', {})
    connections = data.get('connections', [])
    initial_inputs = data.get('inputs', {})

    # Update graph state
    graph_state['nodes'] = nodes

    # Clear and rebuild node functions
    node_functions.clear()
    for node_id, node_info in nodes.items():
        node_id_int = int(node_id)
        code = node_info.get('code', 'def process(): return {}')
        node_functions[node_id_int] = {
            'code': code,
            'function': None
        }

    # Build execution order (topological sort)
    # Simple approach: execute nodes in order of connections
    executed = {}
    outputs = {}

    # Start with initial inputs
    for node_id, inputs in initial_inputs.items():
        executed[node_id] = inputs

    # Execute nodes based on connections
    for conn in connections:
        from_node = str(conn.get('from'))
        to_node = str(conn.get('to'))
        from_port = conn.get('fromPort')
        to_port = conn.get('toPort')

        # If source node hasn't been executed, execute it
        if from_node not in executed:
            node_id_int = int(from_node)
            node_inputs = {}
            # Check if this node has dependencies
            for c in connections:
                if c.get('to') == from_node:
                    # This node depends on another
                    pass

            # Execute the node
            try:
                result = execute_node_internal(node_id_int, node_inputs)
                if result and result.get('success'):
                    executed[from_node] = result.get('output', {})
                else:
                    executed[from_node] = {}
            except Exception as e:
                executed[from_node] = {}

        # Get the output value
        from_output = executed.get(from_node, {})
        value = from_output.get(from_port, None)

        # Prepare input for target node
        if to_node not in executed:
            executed[to_node] = {}
        executed[to_node][to_port] = value

    # Execute any remaining nodes
    for node_id, node_info in nodes.items():
        if node_id not in executed:
            node_id_int = int(node_id)
            try:
                result = execute_node_internal(node_id_int, {})
                if result and result.get('success'):
                    executed[node_id] = result.get('output', {})
            except Exception as e:
                executed[node_id] = {}

    return jsonify({
        'success': True,
        'outputs': executed
    })

def execute_node_internal(node_id, inputs):
    """Internal function to execute a node."""
    node_data = node_functions.get(node_id)
    if not node_data:
        return {'error': f'Node {node_id} not found'}

    # Compile the function if not already compiled
    if node_data['function'] is None:
        node_info = graph_state.get('nodes', {}).get(str(node_id))
        if not node_info:
            return {'error': f'Node info for {node_id} not found'}

        inputs_list = node_info.get('inputs', [])
        outputs_list = node_info.get('outputs', [])

        func = create_node_function(
            node_data['code'],
            node_info.get('name', 'Unknown'),
            node_id,
            inputs_list,
            outputs_list
        )

        if func is None:
            return {'error': 'Failed to compile node function'}

        node_data['function'] = func

    try:
        stdout_capture = io.StringIO()
        sys.stdout = stdout_capture

        # Prepare arguments
        args = []
        node_info = graph_state.get('nodes', {}).get(str(node_id), {})
        for port in node_info.get('inputs', []):
            port_name = port.get('name', 'in')
            args.append(inputs.get(port_name, None))

        result = node_data['function'](*args)

        sys.stdout = sys.__stdout__
        output = stdout_capture.getvalue()

        if result is None:
            result = {}

        return {
            'success': True,
            'output': result,
            'stdout': output
        }
    except Exception as e:
        sys.stdout = sys.__stdout__
        return {
            'error': str(e),
            'traceback': traceback.format_exc()
        }

@app.route('/graph/state', methods=['POST'])
def update_graph_state():
    """Update the full graph state."""
    data = request.json
    graph_state['nodes'] = data.get('nodes', {})
    graph_state['connections'] = data.get('connections', [])
    return jsonify({'success': True})

@app.route('/graph/state', methods=['GET'])
def get_graph_state():
    """Get the current graph state."""
    return jsonify(graph_state)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
