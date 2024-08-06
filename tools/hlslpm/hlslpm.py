import os
import sys


def get_pat():
    pat_filename = os.path.join(os.path.dirname(__file__), "pat.txt")
    if not os.path.exists(pat_filename):
        print("pat.txt not found - create a pat on github and store it here.")
        sys.exit(1)

    with open(pat_filename, 'r') as f:
        return f.read()
    


print(get_pat())


    
