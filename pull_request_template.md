### Q/A checklist

- [ ] I have tested my UI changes on mobile and they look acceptable
- [ ] I have tested changes to the workflows in both the API and the UI
- [ ] I have done a code review of my changes and looked at each line of the diff + the references of each function I have changed
- [ ] My changes have not increased the import time of the server

<details>
<summary>How to check import time?</summary>
<p>

```bash
time python -c 'import server'
```

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

</p>
</details>

### Legal Boilerplate

Look, I get it. The entity doing business as “Gooey.AI” and/or “Dara.network” was incorporated in the State of Delaware in 2020 as Dara Network Inc. and is gonna need some rights from me in order to utilize my contributions in this PR. So here's the deal: I retain all rights, title and interest in and to my contributions, and by keeping this boilerplate intact I confirm that Dara Network Inc can use, modify, copy, and redistribute my contributions, under its choice of terms.
