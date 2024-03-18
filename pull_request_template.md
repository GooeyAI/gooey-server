### Q/A checklist

- [ ] If you add new dependencies, did you update the lock file?
```bash
poetry lock --no-update
```
- [ ] Run tests 
```bash
ulimit -n unlimited && ./scripts/run-tests.sh
```
- [ ] Do a self code review of the changes - Read the diff at least twice.  
- [ ] Carefully think about the stuff that might break because of this change - this sounds obvious but it's easy to forget to do "Go to references" on each function you're changing and see if it's used in a way you didn't expect. 
- [ ] The relevant pages still run when you press submit
- [ ] The API for those pages still work (API tab)
- [ ] The public API interface doesn't change if you didn't want it to (check API tab > docs page)
- [ ] Do your UI changes (if applicable) look acceptable on mobile?
- [ ] Ensure you have not regressed the import time unless you have a good reason to do so. 
You can visualize this using tuna:
```bash
python3 -X importtime -c 'import server' 2> out.log && tuna out.log
```
To measure import time for a specific library:
```bash
$ time python -c 'import pandas'

________________________________________________________
Executed in    1.15 secs    fish           external
   usr time    2.22 secs   86.00 micros    2.22 secs
   sys time    0.72 secs  613.00 micros    0.72 secs
```
To reduce import times, import libraries that take a long time inside the functions that use them instead of at the top of the file:
```python
def my_function():
    import pandas as pd
    ...
```
