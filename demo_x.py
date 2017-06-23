# <markdowncell>
# coding: utf-8

# # Convolutional neural networks for artistic style transfer
# 
# This iPython notebook is an implementation of a popular paper ([Gatys et al., 2015](https://arxiv.org/abs/1508.06576)) that demonstrates how to use neural networks to transfer artistic style from one image onto another. It is meant to go along with a [related blog post](https://harishnarayanan.org/writing/artistic-style-transfer/) that provides more context, and explains a lot of the theory behind the steps that follow.
# 
# There will be a companion blog post and project coming soon in the future that implements a much faster version of this algorithm ([Johnson et al., 2016](https://arxiv.org/abs/1603.08155)) and wraps it in a webapp, a la [Prisma](https://prisma-ai.com).
# 
# <markdowncell>
# # using 2 style images
# python3.5 tensorflow1.2 keras2

# <codecell>


from __future__ import print_function

import time
from PIL import Image
import numpy as np

from keras import backend
from keras.models import Model
from keras.applications.vgg16 import VGG16

from scipy.optimize import fmin_l_bfgs_b
#from scipy.misc import imsave

# <markdowncell>
# ## Load and preprocess the content and style images
# 
# Our first task is to load the content and style images. Note that the content image we're working with is not particularly high quality, but the output we'll arrive at the end of this process still looks really good.

# <codecell>


height = 512
width = 512

content_image_path = 'images/hugo.jpg'
content_image = Image.open(content_image_path)
content_image = content_image.resize((height, width))
content_image


# <codecell>


style_image_path = 'images/styles/wave.jpg'
style_image = Image.open(style_image_path)
style_image = style_image.resize((height, width))
style_image

# <codecell>
#style_image_path2 = 'images/styles/block.jpg'
style_image_path2 = 'images/styles/forest.jpg'
#style_image_path2 = 'images/styles/gothic.jpg'
#style_image_path2 = 'images/styles/marilyn.jpg'
#style_image_path2 = 'images/styles/picasso.jpg'
#style_image_path2 = 'images/styles/scream.jpg'
#style_image_path2 = 'images/styles/starry_night.jpg'
#style_image_path2 = 'images/styles/van_gough.jpg'
#style_image_path2 = 'images/styles/wave.jpg'
style_image2 = Image.open(style_image_path2)
style_image2 = style_image2.resize((height, width))
style_image2

# <markdowncell>
# Then, we convert these images into a form suitable for numerical processing. In particular, we add another dimension (beyond the classic height x width x 3 dimensions) so that we can later concatenate the representations of these two images into a common data structure.

# <codecell>


content_array = np.asarray(content_image, dtype='float32')
content_array = np.expand_dims(content_array, axis=0)
print(content_array.shape)

style_array = np.asarray(style_image, dtype='float32')
style_array = np.expand_dims(style_array, axis=0)
print(style_array.shape)

style_array2 = np.asarray(style_image2, dtype='float32')
style_array2 = np.expand_dims(style_array2, axis=0)
print(style_array2.shape)

# <markdowncell>
# Before we proceed much further, we need to massage this input data to match what was done in [Simonyan and Zisserman (2015)](https://arxiv.org/abs/1409.1556), the paper that introduces the *VGG Network* model that we're going to use shortly.
# 
# For this, we need to perform two transformations:
# 
# 1. Subtract the mean RGB value (computed previously on the [ImageNet training set](http://image-net.org) and easily obtainable from Google searches) from each pixel.
# 2. Flip the ordering of the multi-dimensional array from *RGB* to *BGR* (the ordering used in the paper).

# <codecell>

content_array[:, :, :, 0] -= 103.939
content_array[:, :, :, 1] -= 116.779
content_array[:, :, :, 2] -= 123.68
content_array = content_array[:, :, :, ::-1]

style_array[:, :, :, 0] -= 103.939
style_array[:, :, :, 1] -= 116.779
style_array[:, :, :, 2] -= 123.68
style_array = style_array[:, :, :, ::-1]

style_array2[:, :, :, 0] -= 103.939
style_array2[:, :, :, 1] -= 116.779
style_array2[:, :, :, 2] -= 123.68
style_array2 = style_array2[:, :, :, ::-1]

# <markdowncell>
# Now we're ready to use these arrays to define variables in Keras' backend (the TensorFlow graph). We also introduce a placeholder variable to store the *combination* image that retains the content of the content image while incorporating the style of the style image.

# <codecell>

content_image = backend.variable(content_array)
style_image = backend.variable(style_array)
style_image2 = backend.variable(style_array2)
combination_image = backend.placeholder((1, height, width, 3))

# <markdowncell>
# Finally, we concatenate all this image data into a single tensor that's suitable for processing by Keras' VGG16 model.

# <codecell>

input_tensor = backend.concatenate([content_image,
                                    style_image,
                                    combination_image,
                                    style_image2], axis=0)

# <markdowncell>
# ## Reuse a model pre-trained for image classification to define loss functions
# 
# The core idea introduced by [Gatys et al. (2015)](https://arxiv.org/abs/1508.06576) is that convolutional neural networks (CNNs) pre-trained for image classification already know how to encode perceptual and semantic information about images. We're going to follow their idea, and use the *feature spaces* provided by one such model to independently work with content and style of images.
# 
# The original paper uses the 19 layer VGG network model from [Simonyan and Zisserman (2015)](https://arxiv.org/abs/1409.1556), but we're going to instead follow [Johnson et al. (2016)](https://arxiv.org/abs/1603.08155) and use the 16 layer model (VGG16). There is no noticeable qualitative difference in making this choice, and we gain a tiny bit in speed.
# 
# Also, since we're not interested in the classification problem, we don't need the fully connected layers or the final softmax classifier. We only need the part of the model marked in green in the table below.
# 
# ![VGG Network Architectures](images/vgg-architecture.png "VGG Network Architectures")
# 
# It is trivial for us to get access to this truncated model because Keras comes with a set of pretrained models, including the VGG16 model we're interested in. Note that by setting `include_top=False` in the code below, we don't include any of the fully connected layers.

# <codecell>

model = VGG16(input_tensor=input_tensor, weights='imagenet',
              include_top=False)

# <markdowncell>
# As is clear from the table above, the model we're working with has a lot of layers. Keras has its own names for these layers. Let's make a list of these names so that we can easily refer to individual layers later.

# <codecell>
layers = dict([(layer.name, layer.output) for layer in model.layers])
layers

# <markdowncell>
# If you stare at the list above, you'll convince yourself that we covered all items we wanted in the table (the cells marked in green). Notice also that because we provided Keras with a concrete input tensor, the various TensorFlow tensors get well-defined shapes.
# 
# ---
# 
# The crux of the paper we're trying to reproduce is that the [style transfer problem can be posed as an optimisation problem](https://harishnarayanan.org/writing/artistic-style-transfer/), where the loss function we want to minimise can be decomposed into three distinct parts: the *content loss*, the *style loss* and the *total variation loss*.
# 
# The relative importance of these terms are determined by a set of scalar weights. These are  arbitrary, but the following set have been chosen after quite a bit of experimentation to find a set that generates output that's aesthetically pleasing to me.

# <codecell>

content_weight = 0.015
style_weight = 4.0
style_weight2 = 4.0
total_variation_weight = 0.5


# We'll now use the feature spaces provided by specific layers of our model to define these three loss functions. We begin by initialising the total loss to 0 and adding to it in stages.

# <codecell>
loss = backend.variable(0.)

# <markdowncell>
# ### The content loss
# 
# For the content loss, we follow Johnson et al. (2016) and draw the content feature from `block2_conv2`, because the original choice in Gatys et al. (2015) (`block4_conv2`) loses too much structural detail. And at least for faces, I find it more aesthetically pleasing to closely retain the structure of the original content image.
# 
# This variation across layers is shown for a couple of examples in the images below (just mentally replace `reluX_Y` with our Keras notation `blockX_convY`).
# 
# ![Content feature reconstruction](images/content-feature.png "Content feature reconstruction")
# 
# The content loss is the (scaled, squared) Euclidean distance between feature representations of the content and combination images.

# <codecell>
def content_loss(content, combination):
    return backend.sum(backend.square(combination - content))

layer_features = layers['block2_conv2']
content_image_features = layer_features[0, :, :, :]
combination_features = layer_features[2, :, :, :]

loss += content_weight * content_loss(content_image_features,
                                      combination_features)

# <markdowncell>
# ### The style loss
# 
# This is where things start to get a bit intricate.
# 
# For the style loss, we first define something called a *Gram matrix*. The terms of this matrix are proportional to the covariances of corresponding sets of features, and thus captures information about which features tend to activate together. By only capturing these aggregate statistics across the image, they are blind to the specific arrangement of objects inside the image. This is what allows them to capture information about style independent of content. (This is not trivial at all, and I refer you to [a paper that attempts to explain the idea](https://arxiv.org/abs/1606.01286).)
# 
# The Gram matrix can be computed efficiently by reshaping the feature spaces suitably and taking an outer product.
# 

# <codecell>

def gram_matrix(x):
    features = backend.batch_flatten(backend.permute_dimensions(x, (2, 0, 1)))
    gram = backend.dot(features, backend.transpose(features))
    return gram

# <markdowncell>
# The style loss is then the (scaled, squared) Frobenius norm of the difference between the Gram matrices of the style and combination images.
# 
# Again, in the following code, I've chosen to go with the style features from layers defined in Johnson et al. (2016) rather than Gatys et al. (2015) because I find the end results more aesthetically pleasing. I encourage you to experiment with these choices to see varying results.

# <codecell>

def style_loss(style, combination):
    S = gram_matrix(style)
    C = gram_matrix(combination)
    channels = 3
    size = height * width
    return backend.sum(backend.square(S - C)) / (4. * (channels ** 2) * (size ** 2))

#feature_layers = ['block1_conv2', 'block2_conv2',
#                  'block3_conv3', 'block4_conv3',
#                  'block5_conv3']
#feature_layers = ['block4_conv3', 'block5_conv3']
feature_layers = ['block1_conv2', 'block2_conv2', 'block3_conv3']
#feature_layers = ['block1_conv2', 'block2_conv2']
#feature_layers = ['block1_conv2']
#feature_layers = ['block2_conv2']
for layer_name in feature_layers:
    layer_features = layers[layer_name]
    style_features = layer_features[1, :, :, :]
    style_features2 = layer_features[3, :, :, :]
#    combination_features = layer_features[3, :, :, :]
    combination_features = layer_features[2, :, :, :]
    sl = style_loss(style_features, combination_features)
    sl2 = style_loss(style_features2, combination_features)
#    loss += (style_weight / len(feature_layers)) * sl
    loss = loss + (style_weight / len(feature_layers)) * sl + (style_weight2 / len(feature_layers)) * sl2

# <markdowncell>
# ### The total variation loss
# 
# Now we're back on simpler ground.
# 
# If you were to solve the optimisation problem with only the two loss terms we've introduced so far (style and content), you'll find that the output is quite noisy. We thus add another term, called the [total variation loss](http://arxiv.org/abs/1412.0035) (a regularisation term) that encourages spatial smoothness.
# 
# You can experiment with reducing the `total_variation_weight` and play with the noise-level of the generated image.

# <codecell>

def total_variation_loss(x):
    a = backend.square(x[:, :height-1, :width-1, :] - x[:, 1:, :width-1, :])
    b = backend.square(x[:, :height-1, :width-1, :] - x[:, :height-1, 1:, :])
    return backend.sum(backend.pow(a + b, 1.25))

loss += total_variation_weight * total_variation_loss(combination_image)

# <markdowncell>
# ## Define needed gradients and solve the optimisation problem
# 
# [The goal of this journey](https://harishnarayanan.org/writing/artistic-style-transfer/) was to setup an optimisation problem that aims to solve for a *combination image* that contains the content of the content image, while having the style of the style image. Now that we have our input images massaged and our loss function calculators in place, all we have left to do is define gradients of the total loss relative to the combination image, and use these gradients to iteratively improve upon our combination image to minimise the loss.
# 
# We start by defining the gradients.

# <codecell>

grads = backend.gradients(loss, combination_image)

# <markdowncell>
# We then introduce an `Evaluator` class that computes loss and gradients in one pass while retrieving them via two separate functions, `loss` and `grads`. This is done because `scipy.optimize` requires separate functions for loss and gradients, but computing them separately would be inefficient.

# <codecell>

outputs = [loss]
outputs += grads
f_outputs = backend.function([combination_image], outputs)

def eval_loss_and_grads(x):
    x = x.reshape((1, height, width, 3))
    outs = f_outputs([x])
    loss_value = outs[0]
    grad_values = outs[1].flatten().astype('float64')
    return loss_value, grad_values

class Evaluator(object):

    def __init__(self):
        self.loss_value = None
        self.grads_values = None

    def loss(self, x):
        assert self.loss_value is None
        loss_value, grad_values = eval_loss_and_grads(x)
        self.loss_value = loss_value
        self.grad_values = grad_values
        return self.loss_value

    def grads(self, x):
        assert self.loss_value is not None
        grad_values = np.copy(self.grad_values)
        self.loss_value = None
        self.grad_values = None
        return grad_values

evaluator = Evaluator()

# <markdowncell>
# Now we're finally ready to solve our optimisation problem. This combination image begins its life as a random collection of (valid) pixels, and we use the [L-BFGS](https://en.wikipedia.org/wiki/Limited-memory_BFGS) algorithm (a quasi-Newton algorithm that's significantly quicker to converge than standard gradient descent) to iteratively improve upon it.
# 
# We stop after 10 iterations because the output looks good to me and the loss stops reducing significantly.

# <codecell>

x = np.random.uniform(0, 255, (1, height, width, 3)) - 128.

iterations = 20

for i in range(iterations):
    print('Start of iteration', i)
    start_time = time.time()
    x, min_val, info = fmin_l_bfgs_b(evaluator.loss, x.flatten(),
                                     fprime=evaluator.grads, maxfun=20)
    print('Current loss value:', min_val)
    end_time = time.time()
    print('Iteration %d completed in %ds' % (i, end_time - start_time))

# <markdowncell>
# This took a while on my piddly laptop (that isn't GPU-accelerated), but here is the beautiful output from the last iteration! (Notice that we need to subject our output image to the inverse of the transformation we did to our input images before it makes sense.)

# <codecell>

x = x.reshape((height, width, 3))
x = x[:, :, ::-1]
x[:, :, 0] += 103.939
x[:, :, 1] += 116.779
x[:, :, 2] += 123.68
x = np.clip(x, 0, 255).astype('uint8')

Image.fromarray(x)

# <markdowncell>
# ## Conclusion and further improvements
# 
# It's now your turn to play! Try changing the input images, their sizes, the weights of the different loss functions, the features used to construct them and enjoy different sorts of output. If you end up creating something you truly wish to share, [please do so](https://twitter.com/copingbear)!
# 
# As beautiful as the output of this code can be, the process we use to generate it is quite slow. And no matter how much you speed this algorithm up (with GPUs and creative hacks), it is still going to be a relatively expensive problem to solve. This is because we're solving an entire optimisation problem each time we want to generate an image.
# 
# In an upcoming article (and corresponding iPython notebook), we're going to replace this the optimisation problem with an image transformation CNN, which in turn uses the VGG16 network as before to measure losses. When this transformation network is trained on many images given a fixed style image, we end up with a fully feed-forward CNN that we can apply for style transfer. This gives us a 1000x speed up over this implementation, making it suitable for a the *Stylist* webapp.
# 
# But more on that later.

# <codecell>
#