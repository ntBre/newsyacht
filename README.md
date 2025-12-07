## Motivation

I like the simplicity of newsboat, and it works well, but there are a few
additional features I'm interested in:
- A single feed of all articles
- Visual elements like YouTube thumbnails
- Custom ranking algorithms
- Fun

The first two of these are the main motivation. I guess I'm basically reaching
for something Reddit-esque in appearance but filled with feeds of my own
selection. I think an MVP here would just be a single reverse-chronological
feed, and the third bullet would be a fun additional level to place on top to
experiment with ranking of posts with up- and down-votes[^1].

And then the last point is always a good motivation for hobby projects: having
some fun and learning how RSS works.

## Design

As noted above, I'm just picturing a simple web interface with a list of links
and some metadata where applicable, like a thumbnail for YouTube videos.

I briefly considered using the newsboat database directly, since I think it's
just a simple sqlite database, but I'm not sure how stable the schema is from
version to version, and maybe I'll want to include additional metadata myself.

From talking to GPT, I think RSS is basically as simple as it appears too:
- Fetch some URLs
- Parse some XML
- Store state in a database
- Render the results to the user

Like newsboat, I can just use a cron job to update at an interval, and I think
the rest of this is essentially present in the Python stdlib.

[^1]: I'm reminded of this article I read a long time ago when I was
    experimenting with elfeed for an RSS feed in Emacs:
    https://kitchingroup.cheme.cmu.edu/blog/category/elfeed/. It describes a
    simple scoring function for elfeed entries.
