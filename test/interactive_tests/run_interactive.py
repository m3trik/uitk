import sys
import os
import time

# Ensure we can find mayatk and pythontk in the monorepo structure
SCRIPT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

try:
    from mayatk.env_utils.maya_connection import MayaConnection
except ImportError:
    print("Critical Error: Could not import mayatk.env_utils.maya_connection")
    print(f"Path was: {sys.path}")
    sys.exit(1)

def main():
    print("Initializing Interaction Test for StackedController...")
    
    # 1. Connect to Maya (Launch if needed)
    mc = MayaConnection.get_instance()
    # Using defaults: port 7002
    success = mc.connect(mode="auto", launch=True, force_new_instance=False)
    
    if not success:
        print("ERROR: Could not connect to or launch Maya.")
        sys.exit(1)
        
    print(f"Connected to Maya (Mode: {mc.mode}).")
    
    # 2. Read Payload
    payload_path = os.path.join(os.path.dirname(__file__), "test_stacked_controller_payload.py")
    print(f"Reading payload from: {payload_path}")
    
    with open(payload_path, "r") as f:
        payload_code = f.read()
        
    print("Sending payload to Maya...")
    
    # 3. Execute Payload
    # We increase timeout because launching tests inside Maya might take a moment
    try:
        output = mc.execute(payload_code, capture_output=True, timeout=60)
        
        print("\n" + "-" * 50)
        print("MAYA OUTPUT START")
        print("-" * 50)
        print(output)
        print("-" * 50)
        print("MAYA OUTPUT END")
        print("-" * 50 + "\n")
        
        # Simple heuristic to determine pass/fail based on unittest output
        if output and "OK" in output and "FAILED" not in output:
            print("SUCCESS: StackedController tests passed.")
        else:
            print("FAILURE: StackedController tests failed.")
            sys.exit(1)

    except Exception as e:
        print(f"Execution Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()