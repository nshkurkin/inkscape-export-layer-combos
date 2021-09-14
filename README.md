# Inkscape Plugin: Export Layer Combos
Inkscape v1.2.0+ plugin to export combinations of layers at all once to multiple output images.

## How it works

Open the `Layers` and `XML Editor` tabs. In the `XML Editor` select layer objects and add the attribute `export-layer-combo` to them and given them a value of the form `[group],[selector]`. 

* `[group]` is the name of combination group the layer belongs to. 
* `[selector]` (one of `combo-children`, `visible`, `hidden`) controls the visibility of the layer and how combinations are formed within the group. 

You may also specify a group+selector multiple times in the same attribute as long as each is separated by a semicolon `;`. Here are some examples of different attribute values:

| Layer | Attribute Value | Meaning |
| ----- | ------- | ------- |
| `layer1` | `front,combine-children` | `layer1` is in combination group `front`, and we iteratively combine the immediate children of this layer with the other members of `front`. Only one of the child layers of `layer1` at a time will be visible during each export within the group. |
| `layer2` | `back,visible` | `layer2` is in combination group `back`, and we ensure this layer is always visible for all images exported for the group. |
| `layer3` | `front,hidden` | `layer3` is in combination group `front`, and we ensure this layer is always hidden for all images exported for the group. |
| `layer4` | `front,hidden;back,visible` | `layer4` is hidden in group `front` and visible in group `back`. |

You use the tool by running "**Extensions > Export > Export Layer Combos...**". Once you have configured your settings, you hit `Apply` to generate the combinations.

When you export images, the name of the image is of the form `[group]-[layer-name]-[layer-name]-[...].png`. Suppose you had the following layers:

```
 layer1       -  front,combine-children;back,hidden
    layer1A
    layer1B
 layer2       -  back,visible
 layer3       -  front,hidden
 layer4       -  front,hidden;back,visible
 layer5
```

When you run the tool, it will generate the following images:

```
front-layer1A.png       (layer3 and layer4 are hidden)
front-layer1B.png       (layer3 and layer4 are hidden)
back-layer2-layer4.png  (layer1 hidden)
                        (NOTE: visibility of layer5 is not changed for any export)
```

There are options in the tool to also include the hidden layer names in the exported file name.

## Example
This plugin was developed around exporting a Deck of Playing Cards designed inside of a single Inkscape SVG file. So let's walk through how this plugin can be used to export a Deck of Playing Cards.

<img width="auto" alt="King Queen Jack" src="https://user-images.githubusercontent.com/7967134/133208877-07723938-c473-45aa-9104-9a23cf200239.png">

Basic things you have for a deck:
* The back of the card
* The front of the card
   *  2-10, Jack, Queen, King, Ace 
   *  Suit (hearts, spades, diamonds, clubs)
   *  Joker (note: doesn't have a Suit)

Here is an example of how we could organize our Inkscape SVG around the different parts of the card. We use a series of nested layers representing different aspects of a Playing Card (the Back, the Front, the Suit, the Face).

<img width="321" alt="Example Layer Setup" src="https://user-images.githubusercontent.com/7967134/133210130-24764841-78a1-4309-97fb-eac1241a50e1.png">

To "make" an individual card, we then just hide/unhide certain combinations of layers to make the card. However, this would be tedious for any normal-sized deck (54 cards for a standard playing deck, plus the backside). So let's add the export attributes to the layers we want to combine together.

<img width="323" alt="Setting Attribute on Card Back" src="https://user-images.githubusercontent.com/7967134/133215234-022e403b-c253-4c2e-b835-ff062a71dd32.png">

Here are the settings per layer:

| Layer Name | Attribute Value | Meaning |
| ---------- | --------------- | ------- |
| Card Back  | `back,visible;front,hidden;front-extra,hidden` | Only show this layer when exporting the `back` group. |
| Card Front | `back,hidden` | Only hide this layer when export the `back` group. |
| Face Cards | `front,combo-children;front-extra,hidden` | Combine children of the layer for group `front`, but hide this layer when processing group `front-extra`. |
| Suits      | `front,combo-children;front-extra,hidden` | Combine children of the layer for group `front`, but hide this layer when processing group `front-extra`. |
| Extra Cards | `front,hidden;front-extra,combo-children` | Hide this layer when processing group `front`, but combine children of the layer for group `front-extra`. |

Here are the files exported in this example:

```
back-cardback.png
front-extra-joker.png

front-jack-clubs.png
front-jack-diamonds.png
front-jack-hearts.png
front-jack-spades.png

front-queen-clubs.png
front-queen-diamonds.png
front-queen-hearts.png
front-queen-spades.png

front-king-clubs.png
front-king-diamonds.png
front-king-hearts.png
front-king-spades.png
```
